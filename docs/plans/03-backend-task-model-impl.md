# 方向三：后端任务模型 — 落地实现规范

> 状态：**已落地（P1–P5）** — Job 状态机 + `jobs` 落库 + Scheduler try_start + 取消语义统一  
> 编码对照本文；验收以 §15 手测 + pytest 为准  
> 拍板依据：[03-backend-task-model.md](./03-backend-task-model.md)  
> 依赖：[01-sqlite-data-layer-impl.md](./01-sqlite-data-layer-impl.md)（同一 `binggo.db`、`schema_version`、会话规范）  
> 路线图：[fullstack-roadmap.md](../fullstack-roadmap.md) §3  
> 更新：2026-07-18

本文是编码前的最终规范：约束、状态机、表结构迁移、模块 API、Runner/Scheduler 改写、取消语义、HTTP/前端兼容、落库与清理策略、测试与手测、分期交付。  
**目标红线：** 控制台可感知行为不倒退——单槽互斥、调度撞车 fatal 且永不 cancel 业务、业务动作内部并行保持原样；同时具备 job id、可追溯落库与清晰终态。

---

## 0. 约束摘要（不可违背）

| ID | 约束 |
|----|------|
| T0 | **全局同时仅 1 个业务 Job**（A1）；第二请求拒绝（HTTP 409 / `try_start`→`None`）；**不做**跨 Job 队列；库内**不出现** `queued` |
| T1 | **业务动作内部并行保留**（`refresh_all` / `participate_triple` 等既有 `ThreadPoolExecutor`）；本方向**不改**其并行模型，只加 cancel 检查点 |
| T2 | 调度撞车 **B1**：`CollisionError` → 调度 fatal；调度线程**永不**调用 `cancel()` |
| T3 | 调度划界 **E2**：Scheduler 只 `try_start` + 按 **job id** 等待终态；不直操业务 Store |
| T4 | 持久化 **C2**：try_start 成功即插入 `jobs` 行（`running`）；进度/终态更新同一行；完整日志仍以 `data/logs/binggo.log` 为准 |
| T5 | 历史保留：**最近 7 天**（边角②）；v1 **不做**历史列表 API（边角③） |
| T6 | `log_summary` 截断：**末 16KB**（UTF-8 字节，见 §5.4） |
| T7 | 状态枚举见 §2；库内不存 `idle`；API 可对「从未跑过」合成 `idle` |
| T8 | 取消：仅协作式 `threading.Event`；统一终态 **`cancelled`**（登录取消不再变 `idle`） |
| T9 | **不做**自动重试；**不做**杀线程；任务级超时 DB 字段不做；调度等待超时沿用 `JOB_POLL_TIMEOUT_SEC`（6h） |
| T10 | schema 演进：`SCHEMA_VERSION` **1 → 2**；沿用方向一迁移框架，不用 Alembic |
| T11 | **禁止**在持有 DB 写事务期间发起 B 站 / LLM 网络请求（与方向一 C7 一致） |
| T12 | API **G2**：路径不变；响应增量 `id` / `source` / 规范 `state` 等；前端须适配登录取消态 |
| T13 | 方向二：**只定** JobEvent 形状（§11），本方向不实现 SSE |
| T14 | 密钥不进 `params_json` / `result_json` / `log_summary`（Cookie、token、API Key） |

---

## 1. 拍板对照（实现时勿走样）

| 拍板 | 结论 | 实现落点 |
|------|------|----------|
| A | A1 单槽拒绝 | `JobRunner.try_start`；`POST /api/jobs` → 409 |
| B | B1 撞车 fatal | `AutoScheduler._click_and_wait` 保持 `CollisionError` 语义 |
| C | C2 全生命周期 | `job_store` insert/update；进度节流写库 |
| D | cancelled / interrupted；无 idle/queued 行 | 状态机 §2；启动恢复 §6 |
| E | E2 try_start + 等 job id | `auto_scheduler` 改造 §7 |
| F | 取消做、重试不做 | Runner + `actions` cancel 点 §8 |
| G | G2 + 增量 | `JobStatus.to_dict` / `app.py` §9 |
| H | H2 事件形状 | §11 仅文档约定 |
| ① | 无 queued | insert 即 `running` |
| ② | 7 天历史 | `prune_old_jobs` §5.5 |
| ③ | 无历史 API | 不新增 `GET /api/jobs` 列表 |
| ④ | 16KB summary | `truncate_log_summary` |

---

## 2. 状态机（权威）

### 2.1 库内合法状态

```text
Terminal = {success, error, cancelled, interrupted}
Active   = {running}

try_start 成功 ──► running ──ok──────────────────► success
                     │
                     ├── fail / 未捕获异常 ───────► error
                     │
                     └── 协作式取消成功 ─────────► cancelled

进程启动恢复：WHERE state='running' ──► interrupted
```

| 状态 | 谁写入 | 含义 |
|------|--------|------|
| `running` | `try_start` | 已占槽，worker 执行中（或刚启动尚未跑完） |
| `success` | worker 正常结束且业务 ok | `run_action` 返回且判定成功 |
| `error` | worker | 业务失败、未捕获异常、或取消以外的失败 |
| `cancelled` | worker | 协作式取消（含 `LoginCancelledError`、显式取消路径） |
| `interrupted` | 启动恢复 | 上进程残留的 `running` |

**禁止**写入库：`idle`、`queued`、以及上表以外的字符串。

### 2.2 API 合成态 `idle`

| 场景 | `GET /api/jobs/current` 行为 |
|------|------------------------------|
| 进程内从未成功 `try_start`，且 DB 无任何 job 行 | 返回合成：`state="idle"`，`id=null`，其余空默认（与现初态兼容） |
| 已有终态/历史 | 返回**内存中的当前快照**（通常即最近一次 Job，含终态）；**不是**自动回到 idle |
| 登录取消后 | `state="cancelled"`（**不再**用 `idle`） |

说明：现网 `JobRunner` 在 success/error 后会保持终态直到下一次 start；本方向保持该心智。仅「库空 + 未跑过」需要合成 idle。

### 2.3 转移表（编码必须遵守）

| 从 | 到 | 触发 | 备注 |
|----|----|------|------|
| （无） | `running` | `try_start` 成功 | 插入新行；占槽 |
| `running` | `success` | worker：`ok` 判定为真 | 见 §4.5 |
| `running` | `error` | worker：业务失败 / 异常 | 非取消 |
| `running` | `cancelled` | worker：取消路径 | 见 §8 |
| `running` | `interrupted` | 仅启动恢复 | 不可由 worker 写入 |
| 任意终态 | `running` | 新的 `try_start` | **新行**；旧行不变；内存快照切换到新 id |

非法：终态互相转换；`interrupted` → 其它；对非 `running` 调用 `cancel` 成功（应返回 false）。

### 2.4 成功 / 失败 / 取消判定（worker 出口）

在 `_run_worker` 末尾统一判定，顺序如下：

1. **若捕获 `LoginCancelledError`** → `cancelled`（message 保持「已取消扫码登录」类文案）。  
2. **若捕获异常且（`cancel_event.is_set()` 或 `_is_cancel_exception(exc)`）** → `cancelled`。  
   - `_is_cancel_exception`：消息含「任务已取消」/「已取消」且与取消相关（实现时集中一个小函数，避免误伤）。  
3. **若正常返回 payload**：  
   - `action_ok = payload.get("ok")`；对 `participate` / `participate_triple`，若 `ok is None` 则视为 `False`（保持现逻辑）。  
   - 若 `cancel_event.is_set()` 且（`not action_ok` 或 payload 标明跳过因取消）→ 优先 **`cancelled`**，避免三连取消落成 `error`。  
   - 否则 `success` if `action_ok` else `error`。  
4. **其它未捕获异常** → `error`，`message=friendly_error(exc)`，`log` 用 traceback（再经 sanitize + 截断入库）。

---

## 3. Schema：`SCHEMA_VERSION = 2`

### 3.1 版本动作

```python
# src/db/schema.py
SCHEMA_VERSION = 2
```

注册：

```python
_MIGRATIONS[1] = migrate_v1_to_v2
```

`migrate_v1_to_v2(session)` 必须：

1. 对已存在的 `jobs` 表 **ADD COLUMN**（SQLite 无 IF NOT EXISTS 时先探测 `PRAGMA table_info(jobs)`）。  
2. 新库：`create_all` 已含完整列时，迁移应做成**幂等**（列已存在则跳过）。  
3. **不要**删除旧列；方向一瘦字段全部保留。

### 3.2 `jobs` 表最终列（v2）

| 列 | 类型 | 约束 / 说明 |
|----|------|-------------|
| `id` | INTEGER | PK，自增 |
| `action` | TEXT | 非空；如 `refresh_all` |
| `label` | TEXT | 展示用；可由 `JOB_ACTION_LABELS` + 参与 id 生成 |
| `state` | TEXT | 见 §2.1 |
| `source` | TEXT | `ui` / `auto` / `system`；默认 `ui` |
| `params_json` | TEXT | UTF-8 JSON；可空/`{}`；见 §5.3 脱敏 |
| `progress_step` | INTEGER | 默认 0 |
| `progress_total` | INTEGER | 默认 0 |
| `message` | TEXT | 当前/最终用户可见短消息 |
| `log_summary` | TEXT | 末 16KB；对应内存 `log` 的截断镜像 |
| `result_json` | TEXT | UTF-8 JSON；登录 phase、三连 result 等；过大则截断策略见 §5.4 |
| `error_kind` | TEXT | 可空；建议枚举：`network` / `login` / `business` / `cancelled` / `interrupted` / `internal`；v1 允许只在明显路径填写 |
| `created_at` | INTEGER | Unix 秒；插入时 = started_at（A1 无排队） |
| `started_at` | INTEGER | Unix 秒 |
| `finished_at` | INTEGER \| NULL | 终态时写入 |

**索引（建议）：**

```sql
CREATE INDEX IF NOT EXISTS ix_jobs_state ON jobs(state);
CREATE INDEX IF NOT EXISTS ix_jobs_finished_at ON jobs(finished_at);
CREATE INDEX IF NOT EXISTS ix_jobs_created_at ON jobs(created_at);
```

### 3.3 SQLModel 模型

更新 `src/db/models.py` → `JobRow` 与上表一致。  
注意：`Optional[int]` PK 自增保持与其它表风格一致。

### 3.4 与方向一瘦表的关系

方向一已有：`action, state, progress_*, message, log_summary, created_at, started_at, finished_at`。  
v2 **新增**：`label, source, params_json, result_json, error_kind`。  
迁移只加列，不重建表（避免丢行；开发机 jobs 表目前应为空或极少）。

---

## 4. 模块划分与公开 API

### 4.1 建议文件布局

```text
src/
  db/
    models.py          # JobRow 扩列
    schema.py          # VERSION=2 + migrate_v1_to_v2
  job_store.py         # 新建：jobs 表读写（短事务）
web/
  job_runner.py        # 状态机 + 线程 + 调 job_store；公开 API 增强
  auto_scheduler.py    # E2：try_start + wait_job；仍 B1
  actions.py           # 业务尽量不动；补 refresh 阶段 cancel 点
  app.py               # G2 增量字段；启动时 recover
  static/app.js        # 登录取消：idle → 兼容 cancelled
tests/
  test_job_runner_login.py   # 改编 + 增补
  test_job_store.py          # 新建：落库/截断/prune/恢复
  test_auto_scheduler.py     # 保持撞车/不 cancel；适配 try_start 返回 id
```

不强制新建 `web/tasks/` 大包；若单文件膨胀再拆 `web/job_runner.py` + 私有 helper。

### 4.2 `src/job_store.py`（规范）

职责：**只做 DB**，不含线程、不含 `run_action`。

| 函数 | 行为 |
|------|------|
| `insert_running_job(...) -> int` | 插入 `state=running`，返回 `id` |
| `update_job_progress(job_id, *, step, total, message, log_summary, result_json=...)` | 短事务更新；若行已终态则 **no-op**（防迟到进度） |
| `finish_job(job_id, *, state, message, log_summary, result_json, error_kind, finished_at)` | 仅当当前为 `running` 时更新为终态；否则 no-op 或打日志 |
| `mark_interrupted_running(*, now, message)` | `UPDATE jobs SET state='interrupted', ... WHERE state='running'`；返回影响行数 |
| `prune_old_jobs(*, older_than_unix)` | 删除 `finished_at < older_than` 的终态行；**永不删** `state='running'` |
| `get_job(job_id) -> dict \| None` | 调试/测试用 |
| `get_latest_job() -> dict \| None` | 启动填充内存快照用 |

所有写操作使用方向一的 `session_scope()`（或项目现有等价物）；事务短、单职责。

### 4.3 `JobStatus` / `JobRunner` 公开形状

```python
JobState = Literal["idle", "running", "success", "error", "cancelled", "interrupted"]
JobSource = Literal["ui", "auto", "system"]

@dataclass
class JobStatus:
    id: int | None = None
    state: JobState = "idle"
    action: str = ""
    label: str = ""
    source: JobSource | str = "ui"
    started_at: int | None = None
    finished_at: int | None = None
    message: str = ""
    log: str = ""                 # 完整内存日志（可长于 16KB）
    result: dict[str, Any] | None = None
    progress_step: int = 0
    progress_total: int = 0
    progress_message: str = ""
    # 可选：params 不进 to_dict 默认，除非调试需要

    def to_dict(self) -> dict[str, Any]:
        ...
```

`to_dict()` **增量字段（G2）** 至少包含：

| 字段 | 说明 |
|------|------|
| `id` | int 或 `null` |
| `state` | 含新枚举 |
| `source` | `ui`/`auto`/`system` |
| 既有 | `action,label,started_at,finished_at,message,log,result,progress_*` |

前端未识别的字段应可忽略；**不得删除**既有字段名。

### 4.4 `JobRunner` 方法契约

| 方法 | 契约 |
|------|------|
| `recover_on_startup()` | 调用 `mark_interrupted_running`；`prune_old_jobs`；若内存空则 `get_latest_job` 填快照（终态，不占槽） |
| `is_running() -> bool` | 内存 `state == "running"` |
| `try_start(action, params=None, *, source="ui") -> int \| None` | 忙 → `None`（**不写库**）；成功 → 占槽、插库 `running`、起 daemon 线程、返回 `id` |
| `start(action, params=None, *, source="ui") -> bool` | `try_start(...) is not None`；保持现调用方布尔语义 |
| `cancel() -> bool` | 仅 `running` 时 `cancel_event.set()` 并返回 True；**不立刻改 state**（等 worker 收尾） |
| `get_status() -> JobStatus` | 深拷贝式返回；供 API/调度只读 |
| `wait_until_terminal(job_id, *, timeout_sec, should_stop, poll_interval_sec) -> JobStatus` | 供 Scheduler；轮询直到该 id 非 `running` 或超时/should_stop；**绝不 cancel** |

线程：继续 `threading.Thread(..., daemon=True)`；全局单例 `runner` 保留。

### 4.5 `ok` 判定（保持现逻辑）

```python
action_ok = payload.get("ok")
if action_ok is None and action in {"participate", "participate_triple"}:
    action_ok = False
```

三连「无可参与跳过」现返回 `ok=True` + `result.skipped`——保持，终态为 **`success`**（调度侧仍按 skipped 文案处理）。

---

## 5. 落库与内存双写策略

### 5.1 权威分层

| 层 | 职责 |
|----|------|
| **内存 `JobStatus`** | 热路径；API 轮询主读；完整 `log`；`result` 对象 |
| **SQLite `jobs`** | 耐久；重启恢复；排障；`log_summary` 为截断镜像 |

规则：运行中以内存为准；每次关键进度/终态 **异步于业务** 地短事务刷库（同一进程内同步写即可，但事务必须短）。

### 5.2 写库时机

| 事件 | 写库 |
|------|------|
| `try_start` 成功 | `INSERT` 完整 running 行（含 label/source/params_json） |
| 进度回调 | **节流**：见下 |
| 终态 | `finish_job` 必写 |
| 启动 | `interrupted` + prune + 可选加载 latest |

**进度节流（必须）：**

- 内存：每次 `on_progress` 立即更新。  
- DB：满足任一即刷：  
  - `progress_step` 变化；或  
  - 距上次成功写库 ≥ **1.0 秒**；或  
  - `log_append` 非空且距上次写库 ≥ **1.0 秒**；或  
  - 含 `login_phase` / `qrcode_refreshed_at` 变更（登录体验）。  
- 终态写库不受节流限制。

### 5.3 `params_json` 脱敏

允许入库的键（白名单思路，推荐）：

- `dynamic_id`, `source_id`, `from_auto`  
- 列表筛选相关：与 `_list_filter_params` 一致的键（若有）  
- 其它标量：str/int/bool/float；**单值长度上限**如 500 字符  

禁止或剥离：

- 任何 key 匹配 `(?i)cookie|token|secret|password|authorization|api[_-]?key`  
- 嵌套 dict/list 过深（>2）则只存 `{"_omitted": true}` 或截断说明  

`from_auto`：Scheduler 对 `participate_triple` 继续传 `{"from_auto": True}`；`source` 列另标 `auto`（两者并存：列表示发起方，params 保留业务语义）。

### 5.4 截断规则

| 字段 | 规则 |
|------|------|
| `log_summary` | 取内存 `log` 的 **UTF-8 末 16384 字节**；若截断，前缀加标记如 `…(truncated)\n`（标记本身计入预算或另计，实现选一种并单测） |
| `result_json` | `json.dumps(ensure_ascii=False)` 后若 > **64KB**，改为 `{"_truncated": true, "keys": [...]}` 或保留关键标量键（`login_phase`, `skipped`, `joined`, `failed`）；登录二维码刷新时间戳须尽量保留 |
| 内存 `log` | **不**强制 16KB；完整日志仍主要靠 `binggo.log` |

### 5.5 历史清理（7 天）

```text
cutoff = now_unix - 7 * 86400
DELETE FROM jobs
WHERE state != 'running'
  AND COALESCE(finished_at, created_at, 0) < cutoff
```

触发点：

1. `recover_on_startup()`  
2. 每次 `finish_job` 成功后（可忽略失败，打 debug 日志）  

不做「只保留 N 条」。

### 5.6 与方向一事务纪律

- 进度/终态写 `jobs` **可以**与业务 Store 写交错，但不要包在同一长事务里。  
- Worker 内：先网络与业务 Store，再 `finish_job`。  
- `check_same_thread=False` + WAL 已由方向一配置；jobs 写频繁时依赖节流。

---

## 6. 启动恢复顺序

在 `ensure_user_dirs()` → `init_db()`（升到 v2）之后、对外服务就绪之前：

```text
1. init_db()                    # schema v2
2. runner.recover_on_startup()
   2a. mark_interrupted_running(
         message="进程退出，任务中断",
         error_kind="interrupted",
         finished_at=now,
       )
   2b. prune_old_jobs(cutoff)
   2c. 若内存为初始 idle：get_latest_job() → 填 JobStatus（保持其终态）
3. 接受 HTTP / 调度 start
```

调用点建议：`web/app.py` 在现有 `ensure_user_dirs()` 之后显式 `runner.recover_on_startup()`（`ensure_user_dirs` 已 init_db，勿重复破坏；recover 可幂等）。

**幽灵 running：** 恢复后库内不得残留 `state='running'`（单测断言）。

---

## 7. AutoScheduler 改造（E2 + B1）

### 7.1 保持不变的产品语义

- 允许的 click actions：`refresh_all` / `refresh_watch` / `refresh_status` / `participate_triple`  
- 刷新批次顺序与 soft/hard failure 分类  
- 撞车 → `CollisionError` → `_fatal`  
- **从不** `runner.cancel()`  
- `JOB_POLL_TIMEOUT_SEC` / `JOB_POLL_INTERVAL_SEC` 不变  

### 7.2 `_click_and_wait` 目标伪代码

```text
if runner.is_running():
    raise CollisionError(...)          # 与现一致

job_id = runner.try_start(action, params, source="auto")
if job_id is None:
    raise CollisionError(...)          # 与 start 失败一致

记录 last_click
final = runner.wait_until_terminal(
    job_id,
    timeout_sec=JOB_POLL_TIMEOUT_SEC,
    should_stop=self._stop_event.is_set,   # 或传 Event
    poll_interval_sec=JOB_POLL_INTERVAL_SEC,
)
# 用 final.state / message / result 做 skipped / error 判定
# 注意：cancelled 对调度而言视为异常业务结束还是 soft？
```

**`cancelled` 与调度：** 正常调度路径不应出现业务被 cancel（调度不点取消）。若人手点了取消而调度正在 wait 同一 job——单槽下人手取消的是当前 job，调度 wait 收到 `cancelled`：按 **soft/hard** 规则，建议视为 **hard**（或 `RuntimeError`）以便刷新批次中断并暴露问题；三连被取消同理。实现时在 `_click_and_wait`：

```text
if state == "cancelled":
    raise RuntimeError(msg or "任务已取消")
```

（仍不调用 cancel；只是观察终态。）

### 7.3 `wait_until_terminal` vs 旧 `_wait_until_idle`

| 旧 | 新 |
|----|----|
| 盲等全局 `state != running` | 等 **指定 `job_id`** 进入终态 |
| 登录取消曾变 idle | 终态含 `cancelled`/`interrupted` 均结束等待 |

实现可放在 `JobRunner`（推荐，供复用）或 Scheduler 私有方法读 `get_status()` 且校验 `status.id == job_id`。

若发现 `get_status().id != job_id` 且原 job 已终态：以 `job_store.get_job(job_id)` 为准（防竞态）；A1 下极少发生。

### 7.4 `_probe_job`

增量返回 `job_id`（可空），保持既有 `job_state` 等字段，避免前端调度面板崩。

---

## 8. 取消语义（F）

### 8.1 Runner

- `cancel()` 只 set event，立即返回；HTTP 409 若未 running（保持）。  
- 终态由 worker 判定为 `cancelled`（§2.4）。  
- cancel 后允许立刻再 `try_start`：**仅当**前一 job 已离开 `running`（与现「仍 running 则 409」一致）。若 cancel 已发出但 worker 未收尾，槽仍占 —— 保持。

### 8.2 `actions.py` 检查点（最小改动）

| action | 现状 | 要求 |
|--------|------|------|
| `login` | 已传 `cancel_event` | 保持；Runner 映射 `LoginCancelledError` → `cancelled` |
| `participate_triple` | 多处检查；取消时常 `ValueError("任务已取消")` | 保持抛出；Runner 映射 → `cancelled` |
| `participate` | 较弱 | 在长时间步骤前后加 1～2 处 `cancel_event.is_set()` 检查即可 |
| `refresh_all` | 内部线程池，基本不响应 | **阶段边界**检查：每个 DS future 完成时、流水线步骤之间；set 后尽快结束，勿杀线程 |
| `refresh_source` / `refresh_watch` / `refresh_status` | 弱 | 各自主要循环/步骤间至少 1 处检查 |

取消时返回约定（任选其一，Runner 须识别）：

- **推荐：** `raise ValueError("任务已取消")` 或自定义 `ActionCancelled`（若新增异常，放 `web/actions.py` 或 `src` 小模块，login 的 `LoginCancelledError` 继续专用）。  
- 或 `return {"ok": False, "message": "任务已取消", "cancelled": True}` —— 若用此路径，Runner §2.4 必须认 `cancelled` 键。

**禁止**为取消去 `executor.shutdown(wait=False)` 强杀以外的行为；三连现有 `pending.cancel()` + event 传播可保留。

### 8.3 前端登录取消兼容（必做）

现 `app.js`：

```javascript
if (job.state === "idle" && job.action === "login") { ... }
```

改为同时接受：

```javascript
if (
  job.action === "login" &&
  (job.state === "cancelled" || job.state === "idle")
) { ... }
```

其它 `job.state === "error" | "success" | "running"` 分支保持；`cancelled` 在非登录场景走「结束轮询 + 温和提示」，勿当成功。

---

## 9. HTTP API（G2）

### 9.1 路径（不变）

| 方法 | 路径 | 行为变化 |
|------|------|----------|
| POST | `/api/jobs` | 成功时 `job` 含 `id`/`source`；`source` 默认 `ui`；失败仍 409 |
| GET | `/api/jobs/current` | 同上增量；可能出现 `cancelled`/`interrupted` |
| POST | `/api/jobs/cancel` | 语义不变；返回的 `job` 可能仍为 `running`（取消协作中） |

**不新增** `GET /api/jobs` 列表（边角③）。

### 9.2 `POST /api/jobs` 伪代码

```text
校验 action / 登录 / LLM / params（保持现逻辑）
job_id = runner.try_start(request.action, params, source="ui")
if job_id is None:
    raise HTTPException(409, "已有任务正在运行")
return {"ok": True, "job": runner.get_status().to_dict()}
```

### 9.3 错误码

| 场景 | 码 | detail |
|------|-----|--------|
| 不支持 action | 400 | 保持 |
| 未登录 / 无 LLM | 401 | 保持 |
| 槽占用 | 409 | `已有任务正在运行` |
| 无可取消 | 409 | `当前没有可取消的任务` |

---

## 10. 前端最小改动清单

| 文件 | 改动 |
|------|------|
| `web/static/app.js` | 登录取消识别 `cancelled`（§8.3） |
| 同上 | `handleJobCompletion`：若 `state==="cancelled"`，提示「已取消」，不要走成功刷新 |
| 同上 | 可选：展示 `job.id`（调试用，非必须） |

不强制改轮询间隔；方向二再换 SSE。

---

## 11. JobEvent 形状（H2，仅约定，本方向不实现推送）

供方向二直接复用；Runner 可在写库点预留内部 hook（可选，v1 可不接）：

| event | 何时 | payload |
|-------|------|---------|
| `job.created` | insert running | `{id, action, source, label}` |
| `job.progress` | 节流进度 | `{id, step, total, message}` |
| `job.log` | 可选 | `{id, log}` 或 chunk |
| `job.terminal` | finish | `{id, state, message}`，`state∈{success,error,cancelled,interrupted}` |

v1 编码：**可以只写注释/空 callback 列表**，禁止顺手实现 SSE 端点。

---

## 12. 日志与可观测

- 继续用 `get_logger("job")`：start/cancel/terminal/恢复 打 info；异常 exception。  
- 日志行建议带 `job_id=` / `action=` / `source=`。  
- Scheduler 日志文案尽量不变，便于对照旧手测习惯。

---

## 13. 测试规范

### 13.1 必保产品语义（改编现有）

| 用例 | 断言 |
|------|------|
| 调度撞车 | `is_running` 或 `try_start is None` → `CollisionError`；`cancel` **未被调用** |
| wait 路径 | 等待期间不调用 `cancel` |
| 三连 skip | `success` + skipped 不 fatal |
| 最终 log 覆盖 | `test_final_log_replaces_progress_appends` 仍过 |

### 13.2 新增（`tests/test_job_store.py` / runner）

| 用例 | 要点 |
|------|------|
| try_start 落库 | 成功后 DB 有 `running`→终态行；`id` 一致 |
| A1 拒绝 | running 中第二次 `try_start` 为 `None` 且 **不增行** |
| 登录取消 | `LoginCancelledError` → 内存与 DB 均为 `cancelled`（非 idle） |
| 三连取消 | cancel_event → `cancelled` |
| 启动恢复 | 先手动插一条 `running`，`recover_on_startup` 后变 `interrupted` |
| prune | 插入 `finished_at` 为 8 天前的终态行，prune 后消失；running 保留 |
| log 截断 | 超长 log → `log_summary` ≤ 16KB + 截断标记 |
| params 脱敏 | 含 `cookie` 的 params 不得出现在 `params_json` |
| wait_until_terminal | 只等指定 id；超时抛错 |

全部使用 `isolated_home`（或项目现有 DB 隔离 fixture），**禁止**碰真实 `data/binggo.db`。

### 13.3 不测

- SSE  
- 多 Job 并行  
- 历史列表 API  

---

## 14. 实现分期（建议提交顺序）

| 阶段 | 交付 | 验收要点 |
|------|------|----------|
| **P1** | `JobRow` v2 + `migrate_v1_to_v2` + `job_store` + 截断/prune 单测 | 空库/旧库升级；CRUD |
| **P2** | `JobRunner` 接 store：try_start/id/状态机/recover；API to_dict 增量 | pytest runner；手测 current 含 id |
| **P3** | `AutoScheduler` 改 try_start + wait_by_id；B1 用例全绿 | 调度撞车手测 |
| **P4** | 取消统一 + refresh cancel 点 + `app.js` 登录取消 | 登录取消 → cancelled |
| **P5** | 回归全套 pytest + §15 手测清单 | 签字后再标路线图完成 |

各阶段均可本地运行；**合并心智**以 P5 为准。

---

## 15. 手测验收清单（功能不倒退）

环境：开发机真实 `binggo.db`（先备份或接受 jobs 表被写入）。

- [ ] **单槽：** 一键更新进行中再点三连 → 409/前端提示忙碌  
- [ ] **一键更新：** 多源并行仍工作；完成后 state=success，DB 有对应行  
- [ ] **单源 / 监控 / 状态刷新：** 行为与文案正常  
- [ ] **单条参与 / 三连：** 成功路径正常；三连内部并行保持  
- [ ] **登录成功：** `login_phase` 仍可见；result 合并正常  
- [ ] **登录取消：** UI 关闭二维码；`state=cancelled`（不是成功）；可再登录  
- [ ] **任务取消（三连）：** 终态 `cancelled`，非模糊 error（尽力）  
- [ ] **自动调度：** 空闲时到点触发；手点占用时调度 **fatal**，业务**不被** cancel  
- [ ] **重启：** 若杀进程时有 running，重启后该行 `interrupted`；无幽灵 running  
- [ ] **历史：** 仅验证 DB 中有多行 jobs；无历史 API 亦可  
- [ ] **前端轮询：** 按钮禁用/恢复与进度条正常  
- [ ] **日志文件：** `binggo.log` 仍有完整轨迹  

---

## 16. 非目标（编码时禁止顺手做）

- Celery / Redis / 多进程 worker  
- 短队列（A2）或多 Job 并行（A3）  
- 改写三连/刷新的线程池拓扑  
- `GET /api/jobs` 历史列表、任务中心 UI  
- SSE / WebSocket  
- Alembic  
- 自动重试参与/刷新  
- 把业务结果再存一份「任务结果表」（参与/活动仍走原 Store）  

---

## 17. 风险与对策

| 风险 | 对策 |
|------|------|
| 进度写库拖慢刷新 | 1s/step 节流；事务只更新 jobs |
| 前端仍认 login+idle | §8.3 必改；手测取消登录 |
| 调度 wait 与人手 cancel 交错 | cancelled → RuntimeError；不 cancel 调用 |
| 旧库无新列 | migrate 幂等 ADD COLUMN |
| `result` 过大 | result_json 64KB 降级策略 |
| 测试污染真库 | 坚持 isolated_home |

---

## 18. 编码检查表（PR 自检）

- [ ] `SCHEMA_VERSION == 2` 且 v1→v2 幂等  
- [ ] 无 `queued` 状态写入  
- [ ] A1：忙时不插行  
- [ ] B1：调度测试 `cancel.assert_not_called`  
- [ ] 登录取消 → `cancelled` + 前端兼容  
- [ ] Action 内 ThreadPool 未被「改为单线程」  
- [ ] 无历史列表路由  
- [ ] `log_summary` 截断单测  
- [ ] `recover_on_startup` 清除幽灵 running  
- [ ] 方向一 Store / 参与语义无故意改动  

---

## 19. 文档关系

| 文档 | 职责 |
|------|------|
| [03-backend-task-model.md](./03-backend-task-model.md) | 拍板结论 |
| **本文** | 编码级规范 |
| [01-sqlite-data-layer-impl.md](./01-sqlite-data-layer-impl.md) | DB 引擎/会话/schema 框架 |
| [fullstack-roadmap.md](../fullstack-roadmap.md) §3 | 总览状态 |

---

## 20. 状态

| 项 | 状态 |
|----|------|
| 拍板 A–H + 边角 | ✅ |
| 本文规范 | ✅ 成文 |
| 编码 P1–P5 | ✅ |
| 验收 | ⏳ 建议按 §15 手测；pytest 相关用例已绿 |
