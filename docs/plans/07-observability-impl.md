# 方向七：可观测性 — 落地实现规范

> 状态：**已落地（P1–P4）** — 编码对照本文；验收以 §16 为准  

> 拍板依据：[07-observability.md](./07-observability.md)（**已全部按建议拍板**）  
> 依赖：方向一 `jobs` 表；方向二 SSE（不改协议）；方向三 JobRunner；方向四错误体；方向五前端源码树  
> 路线图：[fullstack-roadmap.md](../fullstack-roadmap.md) §7  
> 更新：2026-07-20

本文是编码前的最终规范：约束、目录、JSONL 字段、contextvars、span 埋点、脱敏、diagnostics API、前端入口、测试、分期与验收。  
**目标红线：**  
1. 可用 `job_id` 从文件日志过滤出单次任务轨迹；  
2. 一键更新路径上各 DS / 流水线阶段有可比 `duration_ms`；  
3. 控制台可导出**脱敏**诊断包；  
4. **不改** Job 状态机、SSE 事件名、任务日志坞行为；不上 ELK / 全量日志进 SQLite。

---

## 0. 约束摘要（不可违背）

| ID | 约束 |
|----|------|
| **O0** | **不改业务语义**：Job 状态机、SSE `job.*`/`auto.*` 协议、UI 任务日志坞（`#log-dock`）行为均不动 |
| **O1** | 落盘 = **仅 JSON Lines 文件**（拍板 **A1**）；**禁止**新建全量日志事件表 |
| **O2** | 完整轨迹仍以文件为准；DB `log_summary` 继续末 **16KB**（方向三 T6） |
| **O3** | Job 工作线程用 **`contextvars` 自动注入** `job_id`/`action`/`job_source`（**D1**） |
| **O4** | 文件 handler 用 JSONL + **写入时脱敏**（**B1 + I1**）；控制台人话格式（**H2**） |
| **O5** | 耗时埋点范围 = Job 起止 + 各 DS + 流水线阶段（**E2**）；**禁止**逐条 `job.progress` 落盘 |
| **O6** | 查询 = 只读 diagnostics API，`tags=["internal"]`（**F2**）；禁止任意路径读盘 |
| **O7** | 诊断包默认脱敏；**不含** Cookie / `llm.env` / 整库 `binggo.db`（**G2**） |
| **O8** | 与日志坞正交（**J1**）；调度与 job 同一文件、同一字段契约（**K1**） |
| **O9** | 持 DB 写事务时**禁止**为埋点打网络；span 只包本地计算/已有业务调用 |
| **O10** | 契约代 1：diagnostics 走统一错误体；**不**改既有 `ErrorCode` 语义（方向四 A11） |

---

## 1. 拍板对照（实现时勿走样）

| 拍板 | 结论 | 实现落点 |
|------|------|----------|
| A | A1 仅 JSONL 文件 | §3 / §4 |
| B | B1 文件全面 JSONL | §4.2 |
| C | C2 字段扩展集 | §5 |
| D | D1 contextvars | §6 |
| E | E2 job+DS+pipeline | §7 |
| F | F2 只读过滤 API | §9 |
| G | G2 控制台诊断包 | §10 / §11 |
| H | H2 文件 JSONL + 控制台人话 | §4.3 |
| I | I1 写入时脱敏 | §8 |
| J | J1 与坞正交 | §0 O0 / §11 |
| K | K1 调度同文件 | §7.4 |
| ① | 轮转 5MB×5；**文件名钉死** | §3.2 |
| ② | 当前文件 + 最近 1 备份；limit≤500 | §9.3 |
| ③ | 默认 INFO；progress 不落盘 | §4.4 / §7 |
| ④ | 行字段 `v: 1` | §5 |
| ⑤ | 概览次要入口 | §11 |
| ⑥ | pytest 为主 | §13 |
| ⑦ | 不做密钥加密 | 非目标 |

---

## 2. 目标目录与文件（编码后应存在）

```text
src/
  app_logging.py              # 改造：JSONL file formatter、人话 console、脱敏钩子、路径常量
  log_context.py              # 新建：contextvars + bind/clear + get_context_fields
  log_span.py                 # 新建：span / log_span helper
  log_redact.py               # 新建：脱敏纯函数（供 formatter 与 bundle 复用）
  log_query.py                # 新建：扫 JSONL、按 job_id 过滤、有界读取
  diagnostics.py              # 新建：组装诊断包文本/结构（无 FastAPI 依赖）
  job_store.py                # 小改：新增 list_recent_jobs(limit)（仅供 diagnostics，非对外历史 API）
  app_paths.py                # 一般不动；版本仍读 __version__ / runtime_label()

web/
  app.py                      # 注册 diagnostics 路由
  job_runner.py               # bind context；job.start / job.end 日志
  actions.py                  # DS / pipeline span
  auto_scheduler.py           # component=auto 的关键日志带上下文字段（能取则取）
  schemas/diagnostics.py      # 新建：查询/bundle 响应模型（可选但推荐）

web/frontend/
  index.html                  # 诊断按钮 DOM
  src/settings/index.ts       # 或新建 src/diagnostics/index.ts：导出/复制
  src/api/client.ts           # 若需可复用 fetchJSON

tests/
  test_log_redact.py
  test_log_context.py
  test_log_jsonl_formatter.py
  test_log_query.py
  test_diagnostics_api.py
```

**禁止：**

- 新建 `job_log_events` 之类全量日志表  
- 把 JSONL 行推入 SSE / 日志坞  
- 在 diagnostics 中返回 `cookies.txt` / `llm.env` 原文  
- 为埋点改 `REFRESH_ALL_TOTAL` 等业务进度语义  

---

## 3. 路径与轮转（边角①）

### 3.1 钉死文件名

| 项 | 值 |
|----|-----|
| 目录 | `{DATA_DIR}/logs`（与现网一致，`ensure_user_dirs` 已 mkdir） |
| **文件名** | **`binggo.log`**（**不改扩展名**） |
| 内容 | **JSON Lines**（每行一个 JSON 对象 + `\n`） |
| 轮转 | `RotatingFileHandler(maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")` |
| 备份名 | 标准库行为：`binggo.log.1` … `binggo.log.5` |

**为何不改名为 `binggo.jsonl`：** 方向一/三文档与安装包用户习惯均指向 `binggo.log`；改的是**内容格式**，不是路径契约。README 须注明「自本版本起内容为 JSONL」。

### 3.2 旧纯文本日志

- 升级后**新进程**写入 JSONL。  
- 旧纯文本行：读侧（`log_query`）**跳过无法 `json.loads` 的行**（兼容轮转边界与升级瞬间）。  
- **不**做自动迁移/转换旧文件。

### 3.3 `DATA_DIR` 绑定注意

当前 `app_logging.py` 使用 `from src.state_store import DATA_DIR`。实现时：

- 保持与现网一致，或改为 `from src.app_paths import DATA_DIR`（二者应同指）；  
- **禁止**在模块 import 时缓存「错误 HOME」：若测试/`BINGGO_HOME` 在 import 后才 patch，formatter 打开的路径须与 `setup_logging()` 调用时的 `DATA_DIR` 一致。  
- 推荐：`setup_logging` 内用**函数**解析 `LOG_DIR = Path(DATA_DIR) / "logs"`，避免长期 stale；若保留模块级常量，则 `isolated_home` / E2E 测试须在 import 前设好 `BINGGO_HOME`（与现 conftest 哲学一致）。

---

## 4. 日志系统改造（`src/app_logging.py`）

### 4.1 对外 API（保持兼容）

```python
def setup_logging(*, level: int = logging.INFO, console: bool = True) -> Path: ...
def get_logger(name: str) -> logging.Logger: ...
```

调用方保持不变：

| 调用方 | console |
|--------|---------|
| `scripts/run_dashboard.py` | 默认 `True`（人话） |
| `web/app.py` 模块加载 | `False` |
| `binggo_launcher.py` | `False` |

`_CONFIGURED` 幂等语义保留：已配置则直接返回路径，**不**重复加 handler。

### 4.2 文件 Formatter（B1）

新建 `JsonLineFormatter(logging.Formatter)`（可放在 `app_logging.py` 或 `log_format.py`）：

1. 组装 dict（§5）；  
2. 对 `msg` 与 `extra` 调用 `redact_text` / `redact_obj`（§8）；  
3. `json.dumps(obj, ensure_ascii=False, separators=(",", ":"))` + 换行；  
4. **禁止**在 JSON 字符串值外出现未转义换行（`msg` 内 `\n` 由 `json.dumps` 转义）。

`RotatingFileHandler.setFormatter(JsonLineFormatter())`。

### 4.3 控制台 Formatter（H2）

当 `console=True`：

- 使用**人话**格式，建议：  
  `"%(asctime)s [%(levelname)s] %(name)s: %(message)s"`  
  若 context 有 `job_id`，可前缀 `[job=%(job_id)s]`（通过 `Formatter` 子类在 `format` 里注入）。  
- 控制台输出也须过脱敏（与 I1 一致，避免终端泄露）。

### 4.4 级别（边角③）

- 根 logger 默认 `INFO`。  
- `span.start` / `span.end` / `job.start` / `job.end`：`INFO`。  
- 调试细节可用 `DEBUG`，默认不落盘到用户机器除非改 level。  
- **禁止**为每次 `job.progress` SSE 打 INFO 文件日志。

### 4.5 LoggerAdapter（可选）

不强制全项目改用 Adapter；优先 **Filter** 或 Formatter 内读取 contextvars，这样现有 `logger.info("…")` 无需改调用点即可带上 `job_id`。

推荐实现：

```text
class ContextFieldsFilter(logging.Filter):
    def filter(self, record):
        for k, v in get_context_fields().items():
            setattr(record, k, v)
        return True
```

挂到 root `binggo` logger（或两个 handler）。Formatter 从 `record` 取字段。

---

## 5. JSONL 字段契约（C2，权威）

### 5.1 行版本

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `v` | int | 是 | 固定 `1`；破坏性变更时升版本，读侧忽略未知字段、跳过不支持的 `v` 可记 warning |

### 5.2 始终写入

| 字段 | 类型 | 说明 |
|------|------|------|
| `ts` | string | **UTC** ISO8601，毫秒可选；推荐 `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")` |
| `level` | string | `record.levelname` |
| `logger` | string | `record.name` |
| `msg` | string | `record.getMessage()` 脱敏后；保持现有中文文案可读 |

### 5.3 Context 自动字段（有则写，无则省略键）

| 字段 | 类型 | 来源 |
|------|------|------|
| `job_id` | int | contextvars |
| `action` | string | contextvars |
| `job_source` | string | `ui` / `auto` / `system` |

**命名：** 用 `job_source`，**不要**用 `source`，以免与数据源 `source_id` 混淆。

### 5.4 条件字段（调用方或 span 提供）

| 字段 | 类型 | 何时 |
|------|------|------|
| `component` | string | `job` / `auto` / `ds` / `pipeline` / `http` / `diagnostics` … |
| `source_id` | string | DS 相关，如 `DS-1`（与 `DS_HANDLER_BY_ID` 键一致） |
| `phase` | string | 见 §7.3 枚举 |
| `duration_ms` | int | span/job 结束 |
| `event` | string | `job.start` / `job.end` / `span.start` / `span.end` / 其它短名 |
| `error_kind` | string | 能取自 Job 终态或异常分类时 |
| `extra` | object | 小 dict；键值均为 JSON 可序列化标量/短字符串 |

### 5.5 `extra` 硬限制

| 规则 | 值 |
|------|-----|
| 顶层键数量 | ≤ 16 |
| 单 string 值最大字符 | 500 |
| 禁止 | 整份活动 list、HTML、cookie 头、响应 body 全文 |
| 序列化失败 | 该键改为 `"<unserializable>"`，不得导致整行丢失 |

### 5.6 示例行

```json
{"v":1,"ts":"2026-07-20T01:23:45.678Z","level":"INFO","logger":"binggo.job_runner","msg":"任务启动","job_id":42,"action":"refresh_all","job_source":"ui","component":"job","event":"job.start"}
```

```json
{"v":1,"ts":"2026-07-20T01:23:50.012Z","level":"INFO","logger":"binggo.actions","msg":"DS-1 检查完成","job_id":42,"action":"refresh_all","job_source":"ui","component":"ds","source_id":"DS-1","phase":"ds_check","event":"span.end","duration_ms":1832}
```

---

## 6. Context 绑定（D1，`src/log_context.py`）

### 6.1 变量

```python
_job_id: ContextVar[int | None]
_action: ContextVar[str | None]
_job_source: ContextVar[str | None]
```

提供：

```python
def bind_job(*, job_id: int, action: str, job_source: str) -> TokenBundle: ...
def reset_job(tokens: TokenBundle) -> None: ...
def get_context_fields() -> dict[str, Any]:  # 仅非 None 字段
```

推荐 `contextmanager`：

```python
@contextmanager
def job_log_context(*, job_id: int, action: str, job_source: str):
    tokens = bind_job(...)
    try:
        yield
    finally:
        reset_job(tokens)
```

### 6.2 绑定点（权威）

**唯一主绑定点：** `JobRunner._run_worker` 函数体最外层：

```text
进入 _run_worker(job_id, action, params, cancel_event)
  source = self._status.source  # 或 get_status().source；须在 worker 内可读
  with job_log_context(job_id=job_id, action=action, job_source=source):
      … 现有 run_action / terminal 逻辑 …
```

`try_start` 线程启动日志若在主线程、此时尚无 worker context：允许该条只有手动字段或仅字符串（可额外 `extra={"job_id": ...}`）；**worker 内**日志必须自动带齐。

### 6.3 线程池传递（关键）

`refresh_all` 使用 `ThreadPoolExecutor`。标准库**不会**把 contextvars 自动传入池线程。

**必须**在提交任务时包装：

```python
ctx = contextvars.copy_context()
fut = executor.submit(lambda: ctx.run(_run_ds_check, ...))
```

或在 `_run_ds_check` 开头再次 `bind_job`（用主线程传入的 job_id/action/job_source 参数）。  
**验收：** 并行 DS 子线程打出的 JSONL 行含相同 `job_id`。

### 6.4 非 Job 路径

启动、账号、设置保存等：不 bind；行中**省略** `job_id` 键（不要写 `null`，减少过滤噪音）。

---

## 7. Span 与埋点范围（E2）

### 7.1 Helper（`src/log_span.py`）

```python
@contextmanager
def log_span(
    name: str,
    *,
    logger: logging.Logger | None = None,
    component: str | None = None,
    source_id: str | None = None,
    phase: str | None = None,
    **extra: Any,
):
    """打 span.start → yield → 成功/异常均打 span.end（含 duration_ms）。"""
```

规则：

- `event=span.start` 可不含 `duration_ms`；`span.end` **必须**含 `duration_ms`（`int`，`round` 或整毫秒）。  
- 异常：`span.end` 仍打，`level=ERROR` 或保持 INFO 且 `extra.error_type=exc.__class__.__name__`；**不吞异常**。  
- `name` 写入 `msg` 或 `extra.span`（钉死一种：**`msg` 用可读中文/英文短句，`extra.span=name` 机器名**）。

机器名 `span` 建议蛇形：`ds_check`、`pipeline_classify`、`job_total`。

### 7.2 Job 起止（`web/job_runner.py`）

| 时机 | event | 要点 |
|------|-------|------|
| worker 开始、`run_action` 前 | `job.start` | `component=job`；msg 可保留「任务启动」 |
| `_apply_terminal` 成功写完 | `job.end` | `duration_ms` = now - started_at；`error_kind` 若有；终态可放 `extra.state` |

**不要**在每个 progress 回调里 `log_span`。

### 7.3 phase 枚举（与现进度文案对齐）

与前端 `REFRESH_ALL_PIPELINE` / actions 进度语义对齐，**不发明第二套业务状态机**：

| `phase` | 含义 | 主要出现位置 |
|---------|------|----------------|
| `ds_check` | 单个 UP 合集检查 | `refresh_all` / `refresh_source` 的 `_run_ds_check` |
| `pipeline_classify` | 分类 | refresh_all/watch 流水线子步 1 |
| `pipeline_detail` | 详情 | 子步 2 |
| `pipeline_persist` | 落库 | 子步 3 |
| `watch_scan` | 监控扫描 | `refresh_watch` |
| `status_refresh` | 本地状态刷新 | `refresh_status` 整段一条 span 即可 |
| `job_total` | 可选，包住整个 worker | 与 `job.start/end` 二选一即可，**避免双计**；推荐只用 `job.start/end` 表示总耗时 |

`source_id`：使用现有 id，如 `"DS-1"` … `"DS-6"`（与 `web/actions.py` 一致）。

### 7.4 埋点植入位置（编码清单）

| 位置 | 动作 |
|------|------|
| `JobRunner._run_worker` | context + `job.start` / `job.end` |
| `actions.refresh_all` → `_run_ds_check` | 每个 DS 一个 `log_span(phase="ds_check", source_id=...)` |
| `actions.refresh_source` | 同上单源 |
| refresh_all / refresh_watch **pipeline** | 三个子步各一 span（可用现有 `_pipeline_substep_index` 文案边界挂钩，或在 pipeline 函数入口/出口包） |
| `refresh_status` | 整段一个 span |
| `refresh_watch` 扫描段 | `phase=watch_scan` |
| `auto_scheduler` | 调度循环关键节点：`component=auto`；若触发 job，job worker 仍走 D1（`job_source=auto`） |

### 7.5 明确不埋

- 每条活动 / 每次 HTTP 底层 retry 细粒（除非 ERROR）  
- SSE 发送路径  
- `update_job_progress` 节流写库  

---

## 8. 脱敏（I1，`src/log_redact.py`）

### 8.1 公共 API

```python
def redact_text(text: str) -> str: ...
def redact_obj(obj: Any) -> Any:  # 递归 dict/list/str；标量原样
```

### 8.2 规则（至少）

对字符串应用（顺序可并列，全部执行）：

| 模式意图 | 替换为 |
|----------|--------|
| `SESSDATA=` 后的值 | `SESSDATA=***` |
| `bili_jct=` / `DedeUserID=` 等常见 Cookie 键 | 同左 `***` |
| `Bearer ` 后的 token | `Bearer ***` |
| `LLM_API_KEY=` / `api_key=` / `Authorization:` 值 | `***` |
| 形如长串 `eyJ…` JWT（可选，长度阈值） | `***` |
| 连续超长 base64（如长度 > 80 且字符集匹配） | `***` |

与 `job_store.sanitize_params` 的密钥键名思路对齐：键名匹配 `(?i)cookie|token|secret|password|authorization|api[_-]?key` 时，dict 值改为 `***`。

### 8.3 应用点

1. `JsonLineFormatter` 写文件前  
2. 控制台 Formatter  
3. `diagnostics` 组装 bundle 时对拼接文本再跑一遍（纵深防御）

### 8.4 测试硬性用例

`tests/test_log_redact.py` 必须覆盖：含 `SESSDATA=foo`、假 API Key、Bearer、普通中文 msg 不被误伤（过度脱敏可接受，**漏脱敏不可接受**）。

---

## 9. 查询与 Diagnostics API（F2）

### 9.1 模块分层

| 模块 | 职责 |
|------|------|
| `src/log_query.py` | 打开日志文件、倒序/正序扫描、parse JSONL、过滤 |
| `src/diagnostics.py` | 拼 bundle：元信息 + jobs 摘要 + 日志行 |
| `web/app.py` + schemas | HTTP 层 |

### 9.2 路由（钉死）

```text
GET /api/diagnostics/logs
GET /api/diagnostics/bundle
```

| 项 | 值 |
|----|-----|
| tags | `["internal"]` |
| include_in_schema | `False`（与 e2e/favicon 等 internal 一致） |
| 登录 | **不要求**登录（本地单机产品；拍板允许） |
| 契约头 | 成功/失败均 `X-Api-Contract`（方向四） |

### 9.3 `GET /api/diagnostics/logs`

**Query：**

| 参数 | 类型 | 默认 | 约束 |
|------|------|------|------|
| `job_id` | int \| 省略 | 省略 | 有则只保留该 `job_id` 行 |
| `limit` | int | 200 | **1～500**（边角②）；超出 → `VALIDATION_ERROR` |
| `q` | string \| 省略 | — | 可选：`msg` 子串包含（大小写不敏感）；实现可二期，v1 **可选实现** |

**扫描范围：**

1. 当前 `{LOG_DIR}/binggo.log`  
2. 若存在 `{LOG_DIR}/binggo.log.1`（最近一份备份）  

读取策略（防爆内存）：

- 从文件**尾部**向前扫（实现可用分块 reverse read，或读入有界字节再解析）；  
- 解析失败的行跳过；  
- 收集匹配行直到 `limit`；返回按 `ts` 或文件顺序**正序**（旧→新）便于阅读。

**成功响应（建议）：**

```json
{
  "ok": true,
  "files": ["binggo.log", "binggo.log.1"],
  "count": 12,
  "lines": [ { "...JSONL对象..." } ]
}
```

### 9.4 `GET /api/diagnostics/bundle`

**Query（可选）：**

| 参数 | 说明 |
|------|------|
| `job_id` | 优先打包该任务日志；省略则最近日志 N 行 + 最近 jobs |

**响应：** 二选一（实现钉死一种，推荐 **A**）：

**A. `text/plain; charset=utf-8` 附件下载**

```text
Content-Disposition: attachment; filename="binggo-diagnostics-YYYYMMDD-HHMMSS.txt"
```

正文为分段纯文本（已脱敏），例如：

```text
=== Binggo diagnostics ===
version: 4.0.2
runtime: dev
platform: Windows-...
exported_at: 2026-07-20T...

=== jobs (recent) ===
...

=== logs ===
{...jsonl...}
{...}
```

**B. JSON** `{ ok, filename, text }` 供前端 `navigator.clipboard.writeText`  

推荐 **A 下载 + 前端同时提供「复制」**（若选 B，复制更简单）。允许实现为：API 返回 JSON `{ ok, text }`，前端既可复制也可 `Blob` 下载——**钉死 JSON 成功体**更利于方向四模型：

```json
{
  "ok": true,
  "filename": "binggo-diagnostics-20260720-012345.txt",
  "text": "=== Binggo diagnostics ===\n..."
}
```

**本文钉死：JSON 成功体（上表）**；前端负责复制与下载。

### 9.5 Bundle 内容清单

| 段 | 内容 | 限制 |
|----|------|------|
| meta | `app_paths.__version__`、`runtime_label()`、`platform.platform()`、导出时间、`DATA_DIR` **仅显示是否自定义 HOME**（可只写 `runtime`/`version`，**不要**打印 Cookie 路径内容） | — |
| jobs | `list_recent_jobs(10)` + 当前 `runner.get_status().to_dict()` | `log_summary` 再截断到 ≤4KB；`params` 已 sanitize |
| logs | 同 logs API，`limit` 默认 300（≤500） | 行已是脱敏 JSON |
| auto | `auto_scheduler.get_status()` 的**瘦快照**（去掉超长 logs 数组或截断） | 可选但推荐 |
| schema | 若有 `schema_version` 可读则附上 | 可选 |

**明确禁止进入 bundle：**

- `config/cookies.txt` 内容  
- `config/llm.env` 内容  
- `binggo.db` 文件字节  
- 未脱敏的 `SESSDATA`

### 9.6 `job_store.list_recent_jobs`

```python
def list_recent_jobs(limit: int = 10) -> list[dict[str, Any]]:
    """按 id 降序，供 diagnostics；不是方向三对外历史 API。"""
```

`limit` 夹在 1～50。不因此开放 `GET /api/jobs/history`。

### 9.7 错误

| 情况 | code |
|------|------|
| limit 非法 | `VALIDATION_ERROR` 400 |
| 日志目录不可读等意外 | `INTERNAL` 500 |
| job_id 无匹配行 | 仍 200，`lines: []`（不是 404） |

---

## 10. 后端接入点小结

### 10.1 `web/job_runner.py`

1. `_run_worker` 外包 `job_log_context`  
2. `job.start` / `job.end` 结构化日志（可用 `logger.info(..., extra=...)` 或专用 helper `log_event`）  
3. 现有 SSE / DB 路径**零语义改动**

### 10.2 `web/actions.py`

1. DS 检查包 `log_span`  
2. pipeline 三阶段包 `log_span`  
3. ThreadPool 提交用 `copy_context().run`（§6.3）

### 10.3 `web/auto_scheduler.py`

- 保持现有用户向 auto 日志进内存/SSE；  
- 文件侧关键 `logger.info` 自动带 filter 字段；调度触发 `try_start(..., source="auto")` 后由 Job worker 绑定 `job_source=auto`。

### 10.4 `web/app.py`

- `setup_logging(console=False)` 保持；  
- 注册 diagnostics 两路由；  
- **不要**把 diagnostics 挂到 E2E 条件上（始终可用，与测试后门不同）。

---

## 11. 前端（G2 / 边角⑤，J1）

### 11.1 DOM 入口

挂在概览 **项目展示**区次要操作（「关于」语义），避免挤占快捷操作主 CTA：

```html
<!-- project-showcase-actions 内，次要按钮 -->
<button type="button" class="btn btn-ghost btn-pill" id="export-diagnostics">
  导出诊断包
</button>
```

**不要**放进 `#log-dock`。

### 11.2 行为

1. 点击 → `GET /api/diagnostics/bundle`（可选带当前 `state.job?.id` 作 `job_id`）  
2. 成功：  
   - 优先 `navigator.clipboard.writeText(text)` + toast「已复制诊断包」；  
   - 并触发 `Blob` + `<a download=filename>` 下载（双保险；剪贴板失败仍可下载）。  
3. 失败：`notify` / `showToast` 展示契约错误 message。  
4. 按钮请求中 disable，防连点。

### 11.3 视觉约束

- 使用现有 `btn btn-ghost btn-pill`；**不**新增大卡片、不改主题色。  
- 不新增「实时日志尾随」面板。

### 11.4 模块放置

推荐新建 `web/frontend/src/diagnostics/index.ts`，在 `main.ts` / bootstrap 绑定 click；保持与 settings/jobs 风格一致（`fetchJSON`）。

---

## 12. 与 SSE / 日志坞的边界（J1）

| 通道 | 继续做什么 | 禁止 |
|------|------------|------|
| SSE `job.log` | 用户可见进度文案 | 推送 JSONL 工程行 |
| `#log-dock` | 展示内存/SSE 任务日志 | 改为读 `/api/diagnostics/logs` |
| JSONL 文件 | 工程排障 + bundle | 驱动进度条 |

---

## 13. 测试规范（边角⑥）

### 13.1 必补 pytest

| 文件 | 断言要点 |
|------|----------|
| `test_log_redact.py` | SESSDATA / Bearer / api_key 被遮；普通中文保留 |
| `test_log_context.py` | bind 后 `get_context_fields`；reset 后清空；嵌套 reset 正确 |
| `test_log_jsonl_formatter.py` | 输出一行合法 JSON；含 context 字段；敏感 msg 已脱敏 |
| `test_log_query.py` | `isolated_home` 下写入临时 JSONL；按 job_id 过滤；坏行跳过；limit |
| `test_diagnostics_api.py` | TestClient：`/api/diagnostics/logs`、`/bundle`；bundle text 不含 `SESSDATA=真实`；契约头 |

### 13.2 不强制

- Playwright 点「导出诊断包」（可手测）  
- 改现有 E2E 五条冒烟  

### 13.3 回归

全量 `pytest`；手动：跑一次 `refresh_status`，确认日志坞仍更新、SSE 仍连。

---

## 14. 文档与仓库说明

编码完成后更新：

| 文档 | 内容 |
|------|------|
| 根 `README.md` 开发者节 | 日志为 JSONL；诊断包入口；路径仍 `data/logs/binggo.log` |
| `docs/plans/07-observability.md` | 状态 → 已落地（编码完成后） |
| 本文件 | 状态 → 已落地；清单勾选 |
| 路线图 §7 | 状态 → 已落地 |

可选：`docs/cli.md` 增加一行「可用 `jq` 过滤：`jq 'select(.job_id==42)' data/logs/binggo.log`」。

---

## 15. 分期交付（P1–P4）

| 期 | 内容 | 完成标准 |
|----|------|----------|
| **P1** | `log_redact` + `log_context` + JSONL Formatter + `setup_logging` 切换；Filter 注入 | 新日志为 JSONL；脱敏单测绿；dashboard 能启动 |
| **P2** | JobRunner context + `job.start/end`；actions DS/pipeline `log_span`；线程池 context 传递 | 一次 `refresh_all`（可 mock DS）文件中出现多条带同一 `job_id` 与 `duration_ms` 的 DS 行 |
| **P3** | `log_query` + `diagnostics` + 两路由 + `list_recent_jobs` | TestClient 全绿 |
| **P4** | 前端按钮 + 复制/下载 + README | 手测导出无密钥；日志坞不回归 |

每期结束：相关 pytest 全绿；不破坏方向六 CI。

---

## 16. 验收（功能 + 工程）

### 16.1 自动

- [ ] `python -m pytest tests/ -q` 含 §13.1 新测全绿  
- [ ] 故意写入含 `SESSDATA=secret` 的 log record → 文件行与 bundle 均为 `***`  
- [ ] `GET /api/diagnostics/logs?job_id=<id>&limit=10` 返回结构合法  

### 16.2 手测

- [ ] `python scripts/run_dashboard.py` → 产生 JSONL 行  
- [ ] 登录态下跑「刷新任务状态」→ 坞正常；文件中有该 `job_id`  
- [ ] 概览点「导出诊断包」→ 复制或下载成功；打开文件无 Cookie/Key 明文  
- [ ] SSE / 进度条 / 终态 toast 与改前一致  

### 16.3 破坏性抽检

- [ ] 删除日志文件后调 logs API → 200 且 `lines=[]`（或自动建空文件后空列表），不 500  
- [ ] `limit=9999` → 400 `VALIDATION_ERROR`  

---

## 17. 实现检查清单（编码中自检）

- [ ] 文件名仍为 `binggo.log`，内容 JSONL  
- [ ] context 在 `_run_worker` 绑定；线程池已 `copy_context`  
- [ ] DS / pipeline 有 `duration_ms`  
- [ ] 无 progress 刷屏落盘  
- [ ] 脱敏在 formatter  
- [ ] diagnostics 为 internal；无任意路径读文件  
- [ ] bundle 无 Cookie / llm.env / db  
- [ ] 未改 SSE 事件名与日志坞  
- [ ] 无 ELK / 无全量日志表  
- [ ] README 已说明  

---

## 18. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 线程池丢失 job_id | §6.3 强制 `copy_context().run`；单测模拟线程池 |
| JSONL 比纯文本略大 | 保持 5MB×5；msg 短；extra 有界 |
| 升级后旧文本行 | 读侧跳过非法 JSON |
| Formatter 异常导致静默无日志 | `format` 内 try/except 回退为最小 JSON `{"v":1,"msg":"formatter_error","level":"ERROR"}` |
| 前端剪贴板权限 | 失败则仅下载 |
| `DATA_DIR` import 时机 | 与 isolated_home / E2E 一致；测试覆盖 |

---

## 19. 非目标（重申）

- OpenTelemetry 全量、Grafana、云日志  
- `GET /api/jobs/history` 产品化  
- 实时日志尾随 UI  
- 用文件日志替换任务日志坞  
- 方向八密钥加密存储  

---

## 20. 状态

| 项 | 状态 |
|----|------|
| 拍板 | ✅ 全部按建议（2026-07-20） |
| 本实现规范 | ✅ 成文 |
| P1–P4 编码 | ✅ 已落地（2026-07-20） |

本地验收：相关单测 + 全量 pytest；前端 build 含「导出诊断包」入口。
