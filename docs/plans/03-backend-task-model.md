# 方向三：后端任务模型 — 拍板记录与设计想法

> 状态：**已拍板**；落地实现规范见 [03-backend-task-model-impl.md](./03-backend-task-model-impl.md)  
> 关联：[全栈路线图 §3](../fullstack-roadmap.md)、[方向一拍板](./01-sqlite-data-layer.md)（已预留 `jobs` 瘦表）  
> 更新：2026-07-18

本文记录两件事：

1. **拍板结论**（产品/工程边界，已定）  
2. **设计想法**（对照现有 `JobRunner` / `AutoScheduler` 的取舍，供实现时对照）

---

## 0. 总前提（已对齐）

| 前提 | 含义 |
|------|------|
| 本地单机 | **不上** Celery / Redis / 多机 worker；进程内即可 |
| 方向一已落地 | 任务元数据落 **同一** `binggo.db`；复用已预留的 `jobs` 表并按需扩列 |
| 产品语义优先 | **不支持多个业务任务并行**；**保留单个业务动作内部的并行**（如 `refresh_all` / 三连里的线程池） |
| 调度撞车语义 | 保持现逻辑：撞车 → 调度 fatal；**永不**由调度 cancel 业务任务 |
| 行为可感知稳定 | 控制台：手点任务、进度/日志、取消登录、自动调度启停，用户可感知行为不倒退 |
| 方向二后置 | 本方向先把状态机与持久化做稳；SSE 推送另开方向二，可共用事件形状 |

---

## 1. 现状摘要（拍板依据）

### 1.1 现有架构

```text
前端 / AutoScheduler
        │
        ▼
  JobRunner（全局单槽，内存 JobStatus + daemon 线程）
        │
        ▼
  web.actions.run_action(action, params, on_progress, cancel_event)
        │
        ▼
  业务内部可 ThreadPool（多源刷新 / 三连等）—— 这不是「多 Job」
```

| 模块 | 路径 | 现状 |
|------|------|------|
| JobRunner | `web/job_runner.py` | 状态：`idle/running/success/error`；无 job id、无队列、无历史 |
| Actions | `web/actions.py` | `login/refresh_*/participate*`；取消支持强制参差 |
| AutoScheduler | `web/auto_scheduler.py` | 独立 daemon；**直连** `runner.start`；撞车 → `CollisionError` → **调度 fatal**；**绝不 cancel** |
| API | `web/app.py` | `POST/GET /api/jobs*`、`/api/auto*`；前端轮询 `GET /api/jobs/current` |
| DB 预留 | `src/db/models.py` → `JobRow` | 方向一已建表，**尚未接入** Runner |

### 1.2 真实痛点（代码级）

| 痛点 | 表现 |
|------|------|
| 互斥靠约定 | UI 与调度抢同一槽；调度撞车即停机 |
| 状态偏内存 | 重启丢失「上次跑什么 / 是否成功」 |
| 取消语义混乱 | 无 `cancelled`；登录取消变 `idle`；三连取消常变 `error` |
| 无可追溯身份 | 无 job id；新任务覆盖旧快照 |
| 职责缠绕 | Scheduler 既排时刻表又同步阻塞等 Job 结束 |

---

## 2. 拍板结论一览（已定）

| 编号 | 议题 | 结论 | 说明 |
|------|------|------|------|
| **A** | 并发与队列 | **A1** | 全局同时仅 **1 个业务 Job**；第二请求拒绝（如 409）；**不做**跨 Job 队列 |
| **B** | 调度撞车 | **B1** | 撞车 → 调度 fatal/stopped；业务继续；用户手动再开调度 |
| **C** | 持久化 | **C2** | 创建即入库，进度/终态更新同一行；保留近期历史 |
| **D** | 状态机 | **按建议 + ①甲** | 引入 `cancelled` / `interrupted`；库内不存 `idle` / `queued`；成功直接 `running` |
| **E** | Runner ↔ Scheduler | **E2** | 调度只投递意图；执行/互斥/等待归任务层；**在 A1 下「投递」= try_start，无排队** |
| **F** | 取消 / 超时 / 重试 | **按建议** | 统一取消令牌 + `cancelled`；**不做**自动重试；超时先复用调度侧 6h 等待，不强制新 DB 字段 |
| **G** | API | **G2 + 增量字段** | 兼容现 `/api/jobs*`；响应增加 `id` / 规范 `state` 等 |
| **H** | 与方向二 | **H2** | 本方向只定 JobEvent 形状；SSE 归方向二 |

### 2.1 A/B 产品语义（你的补充，已写入前提）

> **不支持多个业务并行；支持单个业务内部的并行。**

| 层级 | 是否允许并行 | 例子 |
|------|--------------|------|
| **Job 层**（跨任务） | ❌ 否 | 手点「一键更新」时再点「三连」→ 拒绝；调度撞车 → B1 fatal |
| **Action 内**（同一 Job） | ✅ 是 | `refresh_all` 多源 `ThreadPoolExecutor`；三连多活动并发 — **本方向不改这套内部并行** |

---

## 3. 拍板议题展开（归档）

### 3.1 A — 并发与队列 → **A1**

同时仅一个业务 Job；第二请求拒绝。  
不做短队列（否决 A2），不做多 Job 并行（否决 A3）。

### 3.2 B — 自动调度撞车 → **B1**

保持：撞车 → 调度 fatal；业务继续；**调度线程永不 `cancel()` 业务任务。**

### 3.3 C — 持久化 → **C2**

创建即入库；进度与终态更新同一行；完整日志仍以 `data/logs/binggo.log` 为准；DB 存截断 `log_summary`。

重启恢复：发现残留 `running` → 标为 **`interrupted`**。

历史保留条数/天数 → §8.2。

### 3.4 D — 状态机（建议枚举，已原则同意）

```text
  (try_start 成功)
      │
      ▼
  running ──ok──────────► success
     │
     ├──fail/exception───► error
     │
     └──cancel───────────► cancelled

  进程启动时若发现 running 残留 ──► interrupted
  （库内不存 idle 行）

  （无 queued；拒绝不建行）
```

| 状态 | 含义 |
|------|------|
| `running` | worker 线程执行中 |
| `success` | `run_action` 返回 ok |
| `error` | 业务失败或未捕获异常 |
| `cancelled` | 协作式取消成功（含登录取消） |
| `interrupted` | 进程退出时仍为 running 的恢复标记 |
| `queued` | **不用**（边角①甲） |
| `idle` | **废弃为 API 合成态**（「从未跑过」）；库内不存 |

**明确修正：**

- 登录取消：`idle` → **`cancelled`**（必要时给前端兼容字段）。  
- 三连取消：尽量 **`cancelled`**，不与真实业务失败混为 `error`。

### 3.5 E — 划界 → **E2**（在 A1 下的含义）

```text
AutoScheduler                         TaskService / JobRunner
  到点 ── try_start(job) ───────────►  单槽执行 / 持久化
  按 job id 等待终态 ◄───────────────  忙则 CollisionError（B1）
                                       永不 cancel 业务
```

Scheduler 状态机（`idle/running/stopped/fatal`）可保留；「等任务」基于 **job id**，不盲等「全局 current」。

### 3.6 F — 取消 / 超时 / 重试 → **按建议**

| 能力 | v1 |
|------|-----|
| 取消令牌 | **做**；`refresh_*` 至少阶段边界检查 |
| `cancelled` 状态 | **做** |
| 任务级超时 DB 字段 | **不做**；调度等待超时先复用现有 6h |
| 自动重试 | **不做** |
| 杀线程 | **不做**（仅协作式取消） |

### 3.7 G — API → **G2 + 增量**

保持 `POST /api/jobs`、`GET /api/jobs/current`、`POST /api/jobs/cancel`；增量例如：

```json
{
  "id": 123,
  "state": "running",
  "action": "refresh_all",
  "label": "一键更新",
  "progress_step": 2,
  "progress_total": 5,
  "message": "...",
  "log": "...",
  "result": null,
  "source": "ui"
}
```

历史列表 API 是否 v1 做 → §8.3。

### 3.8 H — 与方向二 → **H2**

预留事件类型（方向二复用）：

| event | 载荷要点 |
|-------|----------|
| `job.created` | id, action, source |
| `job.progress` | id, step, total, message |
| `job.log` | id, chunk 或 full snapshot |
| `job.terminal` | id, state∈{success,error,cancelled,interrupted}, message |

---

## 4. 建议目标形态（已按拍板收束）

一句话：

> **全局单 Job 槽（拒绝并发）+ 明确状态机 + `jobs` 全生命周期落库；调度只 try_start、撞车 fatal、永不 cancel；Action 内并行保持不动；API 兼容现轮询并增量字段。**

### 4.1 模块想象（实现规范再拆）

| 模块 | 职责 |
|------|------|
| `web/job_runner.py`（或薄封装） | 状态机、单槽互斥、线程、cancel、写 DB |
| `web/actions.py` | **业务与内部并行尽量不动**；只加强 cancel 检查点 |
| `web/auto_scheduler.py` | 时刻表 + try_start；撞车按 B1 |
| `src/db/models.py` → `JobRow` | 扩列见 §4.2 / impl |
| 前端 | 先吃新增字段；历史列表视 §8.3 |

### 4.2 扩列方向（默认倾向，可不单独拍板）

| 列 | 用途 | 默认 |
|----|------|------|
| `source` | `ui` / `auto` / `system` | **加** |
| `params_json` | 入参摘要（禁 Cookie/密钥） | **加** |
| `log_summary` | 截断策略 | 默认末 **16KB**（§8.4 可改） |
| `error_kind` | network / login / business / cancelled | 可选，实现时定 |
| `parent_batch_id` | 调度一批关联 | **v1 可不做** |

---

## 5. 非目标（本方向不做）

- Celery / RQ / Redis / 多进程 worker 池  
- 跨 Job 队列（A2）或多 Job 并行（A3）  
- 改写 Action 内部线程池模型（业务内并行保持原样）  
- 集群与跨机器任务分发  
- 任务结果的完整业务数据二次存储  
- 产品级「任务中心」重型 UI  
- 方向二的 SSE 实现  

---

## 6. 设计想法（背景，供对照）

### 6.1 为何现在做方向三

方向一已把数据写稳；任务仍停在「线程 + 内存字典」。没有 job id / 历史难排障；方向二需要稳定的任务事件生产者。

### 6.2 为何坚持 A1 + B1（你的选择）

与现控制台心智一致：「一次干一件事」；撞车必须醒目（调度停机），避免静默堆积或误 cancel。  
代价：手点与调度仍可能撞车——这是**有意保留**的产品摩擦，不是实现疏漏。

### 6.3 业务内并行 vs 多 Job

`actions.py` 里多源刷新、三连等已用线程池，那是**一个 Job 内部的吞吐**，写库仍由该 Job 的编排控制。  
多 Job 并行才会把「两个编排同时写活动/参与库」的风险拉回来——已拍板禁止。

### 6.4 与 `run_action` 的边界

`run_action` 继续当纯执行器（加 cancel 点）；任务抽象不把抽奖逻辑吸进 Job 类。

### 6.5 测试遗产

保留「调度不 cancel 业务」「撞车 fatal」等产品语义断言；新增状态机/落库/重启恢复用例。

---

## 7. 拍板后建议回归范围（功能不倒退）

- [ ] 手点：一键更新 / 单源 / 监控同步 / 状态刷新  
- [ ] 手点：单条参与、三连参与；**内部并行行为与现网一致**  
- [ ] 登录扫码：成功、取消 → `cancelled`  
- [ ] 自动调度：到点触发；与手点并发 → **B1 fatal**，业务不被 cancel  
- [ ] 第二 Job 请求被拒绝（A1）  
- [ ] 重启进程：无幽灵 `running`；近期任务可查  
- [ ] 前端：现有轮询仍可用（G2）  
- [ ] 相关 pytest 改编后通过  

---

## 8. 边角拍板（已定）

| 编号 | 议题 | 结论 |
|------|------|------|
| **①** | `queued` | **甲：不用**；try_start 成功直接 `running`；拒绝不建行 |
| **②** | 历史保留 | **乙：最近 7 天** |
| **③** | 历史列表 API | **甲：v1 不做**；只保证 `current` + DB 可查 |
| **④** | `log_summary` | **末 16KB** |

### 8.1 默认可由实现者定（已写入 impl）

| 项 | 默认倾向 |
|----|----------|
| 模块落点 | 先强化 `web/job_runner.py` + `src/job_store.py`（或 `src/db/job_store.py`） |
| `source` / `params_json` / `result_json` / `label` | 做 |
| `parent_batch_id` | v1 不做 |
| cancel 后允许立刻再 start | 保持现行为 |
| Action 内 ThreadPool | **不改** |
| schema 升级 | `schema_version` 1 → 2 |

---

## 9. 实现分期想象（边角拍板后写入 impl，非现在开工令）

| 阶段 | 交付 |
|------|------|
| P1 | 状态机 + `JobRow` 扩列/迁移 + 写入路径 |
| P2 | JobRunner 接 DB；`/api/jobs*` 兼容增强（id/state） |
| P3 | AutoScheduler 改为 try_start + 按 job id 等待；落实 B1 |
| P4 | 取消语义统一；refresh 阶段 cancel 点 |
| P5 | 重启恢复 + 历史保留 + 测试/手测 |

---

## 10. 文档关系

| 文档 | 职责 |
|------|------|
| [fullstack-roadmap.md](../fullstack-roadmap.md) §3 | 十方向总览中的条目 |
| **本文** | 拍板边界与设计想法 |
| `03-backend-task-model-impl.md`（待写） | 拍板后的编码级规范 |
| [01-sqlite-data-layer.md](./01-sqlite-data-layer.md) | `jobs` 瘦表预留来源 |

---

## 11. 状态

| 项 | 状态 |
|----|------|
| 现状梳理 | ✅ |
| 拍板 A–H | ✅ 已定（见 §2） |
| 边角 ①～④ | ✅ 甲 / 乙(7天) / 甲 / 16KB |
| 落地实现规范 | ✅ [03-backend-task-model-impl.md](./03-backend-task-model-impl.md) |
| 编码 | ✅ 已按 impl 落地 |

讨论记录：

| 日期 | 内容 |
|------|------|
| 2026-07-18 | 初稿：建议 A2+B3+… |
| 2026-07-18 | 拍板：A1、B1、C2、D 按建议、E2、F 按建议、G2+增量、H2；明确「多业务不并行、业务内并行保留」 |
| 2026-07-18 | 边角：queued 不用；历史 7 天；无历史 API；log_summary 16KB；成文 impl |
