# 方向二：实时进度 — 落地实现规范

> 状态：**已落地（P1–P6）** — EventHub + `/api/events` SSE + Job/Auto 发布 + 前端 H2 回退  
> 编码对照本文；验收以 §13 手测 + pytest 为准  
> 拍板依据：[02-realtime-progress.md](./02-realtime-progress.md)  
> 依赖：[03-backend-task-model-impl.md](./03-backend-task-model-impl.md)（Job 状态机 / JobEvent 名 / Runner 钩子点）  
> 路线图：[fullstack-roadmap.md](../fullstack-roadmap.md) §2  
> 更新：2026-07-18

本文是编码前的最终规范：约束、事件目录、EventHub、SSE 协议、Job/Auto 发布点、前端订阅与 H2 回退、测试与手测、分期交付。  
**目标红线：** 控制台可感知行为不倒退——任务进度/日志/登录二维码/终态处理与调度监视面板体验不差于现轮询；断线可回退 REST；调度业务语义（撞车 fatal、永不 cancel 业务）不变。

---

## 0. 约束摘要（不可违背）

| ID | 约束 |
|----|------|
| R0 | 传输只用 **SSE**（A1）；**不上** WebSocket / Redis / 消息总线 |
| R1 | **一条流** `GET /api/events` 同时承载 `job.*` 与 `auto.*`（边角①甲） |
| R2 | 保留 `GET /api/jobs/current` 与 `GET /api/auto/status`（C2 + 边角④）；作首屏、重连对齐、H2 回退 |
| R3 | Job 事件名 **沿用方向三**：`job.created` / `job.progress` / `job.log` / `job.terminal`；另增 `job.snapshot` |
| R4 | Job 日志 **E2**：热路径推 `chunk`；重连用 current 对齐；terminal 可带最终 log |
| R5 | Auto：**变更推 `auto.snapshot`**；新日志推 **`auto.log` 增量**（边角②③） |
| R6 | 进程级订阅（F2）；多标签多订阅者；单订阅者队列深度 **256** |
| R7 | 溢出策略：可丢旧 `progress`/`job.log`/`auto.log`；**不丢** `job.terminal`；Auto 保 **fatal/stopped 类 snapshot** 与**最新一条** `auto.log`（G + 边角⑤） |
| R8 | 心跳 **15s**；前端 H2：SSE 优先，失败回退 Job 轮询 + Auto 2s 轮询 |
| R9 | 倒计时 **不**每秒推送；本地 1s timer；snapshot 带 `next_slot` / `server_now_unix` 校准 |
| R10 | 启停调度、启停任务、取消：**仅 REST POST**；SSE 只下行 |
| R11 | 发布路径 **禁止**在持有 DB 写事务时做网络；hub 发布必须 **非阻塞**（入队即返回） |
| R12 | v1 **不做** `Last-Event-ID` 事件溯源；重连 = REST 快照 + 继续收流 |
| R13 | 不改方向三任务语义（单槽、B1 撞车、cancelled 等）；本方向只加推送 |
| R14 | 密钥/Cookie **不得**出现在 SSE data 中 |

---

## 1. 拍板对照（实现时勿走样）

| 拍板 | 结论 | 实现落点 |
|------|------|----------|
| A | A1 SSE | `StreamingResponse` + `text/event-stream` |
| B | B2 Job+Auto | 同一 hub、同一 `/api/events` |
| C | C2 保留 current | 不删 `/api/jobs/current` |
| D | D2 JobEvent | 事件名 §3 |
| E | E2 增量日志 | `job.log.chunk` |
| F | F2 进程流 | 订阅不强制 job_id |
| G | 心跳/多订阅/有界 | `EventHub` §4 |
| H | H2 回退轮询 | `app.js` §9 |
| ① | 单端点 | `/api/events` |
| ② | auto.snapshot | Scheduler 发布 §7 |
| ③ | auto.log 增量 | `_log` 挂钩 |
| ④ | 保留 auto/status | `app.py` 不动删除 |
| ⑤ | 溢出保底 | hub 丢弃策略 §4.4 |

---

## 2. 模块与文件布局

```text
web/
  event_hub.py          # 新建：EventHub、事件封装、全局单例
  sse.py                # 新建（可选）：SSE 编码与 StreamingResponse 生成器
  job_runner.py         # 改造：created/progress/log/terminal/snapshot 发布
  auto_scheduler.py     # 改造：snapshot / auto.log 发布（节流）
  app.py                # 新增 GET /api/events；保留 current/auto/status
  static/app.js         # EventSource 订阅 + H2 回退；复用 UI 更新函数
tests/
  test_event_hub.py     # 新建
  test_sse_events.py    # 新建：路由/格式（可用 TestClient stream）
  # 既有 job/auto 测试不得被破坏
```

依赖：标准库即可；**不新增**第三方 SSE 包（除非现有栈已有且必要）。

---

## 3. 事件目录（权威）

所有事件经 hub 广播。SSE 帧：

```text
id: <单调递增整数，可选但推荐>
event: <下表 event 名>
data: <单行 JSON，UTF-8；禁止 data 内裸换行，JSON 内 \n 转义>

```

（空行结束一帧。）

### 3.1 通用信封（data JSON 建议字段）

| 字段 | 类型 | 说明 |
|------|------|------|
| `ts` | int | Unix 秒；服务端生成 |
| `seq` | int | hub 全局单调序号（与 SSE `id:` 一致） |
| … | | 事件特有字段 |

### 3.2 Job 事件

#### `job.snapshot`

**何时：** SSE 连接建立后立刻（若有当前/最近 job）；前端显式需要对齐时也可再发（可选）。  
**载荷：**

```json
{
  "ts": 1710000000,
  "seq": 12,
  "id": 42,
  "state": "running",
  "action": "refresh_all",
  "label": "一键更新活动链接",
  "source": "ui",
  "message": "…",
  "log": "…",
  "result": {"login_phase": "waiting"},
  "progress_step": 1,
  "progress_total": 9,
  "progress_message": "…"
}
```

形状对齐 `JobStatus.to_dict()`；`id` 可为 `null`（合成 idle）。

#### `job.created`

**何时：** `try_start` 成功且已获得 `job_id` 之后。  
**载荷：** `{ts, seq, id, action, source, label}`

#### `job.progress`

**何时：** 内存 progress 更新时（可比写库更勤；见 §6.2）。  
**载荷：**

```json
{
  "ts": 0, "seq": 0,
  "id": 42,
  "step": 2,
  "total": 9,
  "message": "…",
  "result": {"login_phase": "waiting", "qrcode_refreshed_at": 1710000001}
}
```

规则：

- `result`：**仅当有变更时附带**（至少登录相关键）；不要每次塞完整巨大 result。  
- 无 `log` 全量（日志走 `job.log`）。

#### `job.log`

**何时：** `on_progress` 含非空 `log_append`（sanitize 后）。  
**载荷：** `{ts, seq, id, chunk: "追加文本"}`  
**禁止**把整份历史 log 每次重推（E2）；terminal/snapshot 才可带全量。

#### `job.terminal`

**何时：** `_apply_terminal` 内存终态已写入之后（与 API 可见顺序一致：先内存终态，再 publish；或与 `_apply_terminal` 末尾同步）。  
**载荷：**

```json
{
  "ts": 0, "seq": 0,
  "id": 42,
  "state": "success",
  "action": "refresh_all",
  "message": "…",
  "log": "最终日志（可选，推荐带）",
  "result": {}
}
```

`state∈{success,error,cancelled,interrupted}`。

### 3.3 Auto 事件

#### `auto.snapshot`

**何时：** 调度状态「有意义变更」后（§7.2）；SSE 连接建立时若调度非纯初始也可推一帧。  
**载荷：** 以 `AutoScheduler.get_status()` 为基，但 **logs 裁剪**：

| 字段 | 处理 |
|------|------|
| `state,state_label,message,fatal_error,current_phase,next_hint` | 原样 |
| `next_slot, refresh_pipeline, last_click, job_probe` | 原样 |
| `server_now, server_now_unix` | 原样（供校准） |
| `schedule` | 可带（静态）；或省略以缩小体积（实现二选一，**推荐带**以免前端缺字段） |
| `logs` | **最多最近 30 条**（或 0 条：若本帧仅为 phase 抖动且刚推过 log——见节流）；完整 logs 以 REST 为准 |
| `started_at,stopped_at,last_tick_at,*_key` | 原样 |

外加信封 `ts/seq`。

#### `auto.log`

**何时：** `_log` 追加一条之后。  
**载荷：** `{ts, seq, level, message, log_ts}`  
其中 `log_ts` 为调度日志条目原有时间字符串（若有），避免与信封 `ts` 混淆。

### 3.4 心跳

两种实现任选其一（推荐 A）：

| 方案 | 格式 |
|------|------|
| **A** | SSE 注释行：`: ping\n\n`（每 15s） |
| **B** | `event: heartbeat` + `data: {"ts":…}\n\n` |

心跳 **不占用**「可丢事件」配额（不入有界业务队列，或单独发送）。

### 3.5 禁止的事件用途

- 不通过 SSE 下发「请取消任务」「请停止调度」等控制指令。  
- 不推送 Cookie、LLM key、完整 cookies 文本。

---

## 4. EventHub 规范

### 4.1 职责

进程内单例：接收 `publish(event_name, payload_dict)`，向所有订阅者投递。

```python
# web/event_hub.py（概念 API）
class EventHub:
    def publish(self, event: str, data: dict[str, Any]) -> None: ...
    def subscribe(self) -> Subscriber: ...          # 返回带 Queue 的订阅句柄
    def unsubscribe(self, sub: Subscriber) -> None: ...

@dataclass
class HubEvent:
    seq: int
    event: str
    data: dict[str, Any]   # 已含 ts/seq
```

### 4.2 线程安全

- `publish` 可从 Job worker 线程、Scheduler 线程、主线程调用。  
- 使用 `threading.Lock` 保护订阅者列表与 `seq`。  
- 向每个订阅者 `queue.put_nowait`；**禁止**在 publish 里 `join`/网络 IO。

### 4.3 订阅者队列

| 项 | 值 |
|----|-----|
| 类型 | `queue.Queue(maxsize=256)` 或 `collections.deque` + 条件变量 |
| 深度 | **256** |
| 关闭 | SSE 生成器结束 / 客户端断开 → `unsubscribe` + 毒丸或关闭标志 |

### 4.4 溢出丢弃策略（关键）

当某订阅者队列满时：

1. **扫描队列**（或维护侧车结构）识别：  
   - **保留：** 所有 `job.terminal`；`auto.snapshot` 且 `state in {fatal, stopped}`（或 data 含非空 `fatal_error`）；**最新一条** `auto.log`  
   - **可丢：** `job.progress`、`job.log`、`job.created`（已过时）、普通 `auto.snapshot`、旧 `auto.log`、`job.snapshot`  
2. 丢最旧的可丢事件直到能 `put` 新事件。  
3. 若新事件本身是 `job.progress` 且仍满：允许丢弃新 progress（保 terminal）。  
4. 若新事件是 `job.terminal`：必须放入（可丢多个 progress/log 腾地方）。

实现允许「简化版」：  
- 队列满 → 丢队头直到能放；但若队头是 terminal/fatal snapshot 则跳过队头丢下一个；  
- 单元测试必须覆盖「满队列时 terminal 不丢」。

### 4.5 seq

全局 `itertools.count(1)` 或自增 int；写入 `data["seq"]` 与 SSE `id:`。

### 4.6 全局单例

```python
event_hub = EventHub()
```

测试可构造独立 hub 注入，避免污染。

---

## 5. SSE 端点规范

### 5.1 路由

```http
GET /api/events
Accept: text/event-stream
```

- 响应头至少：  
  - `Content-Type: text/event-stream; charset=utf-8`  
  - `Cache-Control: no-cache`  
  - `Connection: keep-alive`  
  - （若有反向代理）`X-Accel-Buffering: no`  
- **禁用**中间层缓冲；FastAPI/`StreamingResponse` 生成器即时 yield。

### 5.2 连接生命周期

```text
1. subscribe()
2. 立即发送：
   - job.snapshot（runner.get_status().to_dict()）
   - auto.snapshot（裁剪 logs 后的 get_status()）—— 若实现选择「仅当 auto 非完全冷启动」亦可总是发
3. loop:
   - 等待 queue 事件或心跳到期
   - yield 编码帧
4. 客户端断开 / GeneratorExit → unsubscribe
```

### 5.3 编码函数

```python
def format_sse(event: str, data: dict, *, event_id: int | None = None) -> bytes:
    # id: {event_id}\n
    # event: {event}\n
    # data: {json.dumps(data, ensure_ascii=False, separators=(",", ":"))}\n
    # \n
```

JSON 必须单行；`ensure_ascii=False`。

### 5.4 与 TestClient

流式测试可用 `client.stream("GET", "/api/events")` 读若干字节后关闭；或对 hub 单测为主、路由测「Content-Type + 首帧含 snapshot」。

### 5.5 不做的查询参数（v1）

- `?job_id=` 过滤：可选后续；v1 全量进程流即可。  
- `Last-Event-ID`：不做重放。

---

## 6. JobRunner 发布点

### 6.1 挂钩位置（必须）

| 时机 | 事件 |
|------|------|
| `try_start` 成功赋 `job_id` 后、启动线程前或后（尽早） | `job.created` |
| `_make_progress_callback` 更新内存后 | `job.progress`（§6.2）；若有 log_append → 另发 `job.log` |
| `_apply_terminal` 内存状态已改为终态后 | `job.terminal` |

可选：`recover_on_startup` 后不强制广播（无订阅者）；有订阅者连上时靠连接时 snapshot。

### 6.2 progress 发布频率

- **每次**内存 progress 字段变化都可 publish（含 login_phase / qrcode 变更）。  
- 若同一次回调 step/message 都不变且无 result/log 变更：不发。  
- **不要**用写库节流限制推送；写库失败不影响 publish。

### 6.3 发布失败

`publish` 内部吞掉订阅者级异常并打 debug/warning；**不得**让业务 action 失败。

### 6.4 与方向三顺序

推荐 `_apply_terminal` 顺序：

1. 写 DB（含重试逻辑，保持现实现）  
2. 更新内存终态  
3. `publish(job.terminal)`  

这样 SSE 与随后 `GET current` 一致。若 DB 失败仍更新内存（现逻辑），仍应 publish terminal。

### 6.5 依赖方向

仅 `import event_hub`；**禁止** hub 反向 import runner 造成环（snapshot 在 SSE 层读 runner）。

---

## 7. AutoScheduler 发布点

### 7.1 挂钩位置

| 时机 | 事件 |
|------|------|
| `_log(...)` 追加一条后 | `auto.log` |
| `_set_phase` / `_fatal` / `start` / `stop` 导致状态字段变化后 | `auto.snapshot`（节流见下） |
| `last_click` / `refresh_pipeline` / `*_key` 更新后 | 纳入 snapshot 节流 |
| 等待 job 时频繁改 `current_phase` 文案 | snapshot **节流** |

### 7.2 snapshot 节流（必须）

避免 wait 循环每 2s 刷爆：

| 规则 | 值 |
|------|-----|
| 最短间隔 | **500ms** 内合并为一次（trailing：到期发最新） |
| 立即发送（绕过间隔） | `state` 变为 `fatal` / `stopped` / `running←idle` / `idle←running`；或 `fatal_error` 从空变非空 |
| 载荷 | 调用与 `get_status()` 相同的组装，再裁剪 `logs` |

实现建议：`_schedule_auto_snapshot(force: bool = False)`。

### 7.3 auto.snapshot 与 auto.log 分工

- 新日志：**只**走 `auto.log`，不必每次 snapshot 带全 logs。  
- snapshot 中 `logs`：裁剪最近 30 条作「面板保险」；前端应以增量拼本地缓冲，重连用 REST 全量覆盖。

### 7.4 前端本地倒计时

- snapshot 提供 `next_slot.at_unix` 与 `server_now_unix`。  
- `tickAutoCountdown` 保留；不要为倒计时每秒 publish。

### 7.5 业务语义

发布不得调用 `runner.cancel`；不得改变 CollisionError / fatal 行为。

---

## 8. HTTP / REST 共存

| 方法 | 路径 | 本方向 |
|------|------|--------|
| GET | `/api/events` | **新增** SSE |
| GET | `/api/jobs/current` | **保留** |
| POST | `/api/jobs` | 保留 |
| POST | `/api/jobs/cancel` | 保留 |
| GET | `/api/auto/status` | **保留** |
| POST | `/api/auto/start` `/stop` | 保留 |

`/api/summary` 内嵌 `job` 字段可继续；不强制改。

---

## 9. 前端规范（`app.js`）

### 9.1 订阅状态机（H2）

```text
页面就绪
  → GET /api/jobs/current + GET /api/auto/status（首屏）
  → 打开 EventSource("/api/events")
  → 若 EventSource 报错 / 心跳超时（如 45s 无任何帧）
        → 关闭 ES，startPolling() + ensureAutoPolling()
        → 可选：稍后重试 ES，成功则 stopJobPolling / stopAutoPolling（调度在 running/监视时）
```

心跳超时：若用 comment ping，`EventSource` 可能不暴露 comment；更稳妥用 **`heartbeat` 事件** 或依赖「任意 event 刷新 lastActive」。  
**推荐：** 心跳用 `event: heartbeat`，前端重置计时器；45s 无消息 → 判死切回退。

### 9.2 事件处理

| 事件 | 处理 |
|------|------|
| `job.snapshot` / `job.progress` | 合并到本地 job 视图 → `updateJobUI`；登录二维码逻辑复用（读 `result`） |
| `job.log` | 将 `chunk` append 到本地 log 字符串（注意去重：若 snapshot 已含全量则覆盖） |
| `job.created` | 可重置本地 log 缓冲；`updateJobUI` 初态 |
| `job.terminal` | `updateJobUI`；然后走与轮询相同的完成分支（`handleJobCompletion` / 登录 cancelled） |
| `auto.snapshot` | `renderAutoDock(payload)`（注意 payload 可能无完整 logs） |
| `auto.log` | 把一行 append 进面板日志 UI（若 `renderAutoDock` 依赖整数组，维护 `state.autoLogs` 缓冲） |
| `heartbeat` | 刷新 lastActive |

### 9.3 与旧轮询互斥

- SSE 健康时：**不要**同时 `startPolling`（避免双通道打架）。  
- 调度：SSE 健康且用户打开监视时，**停** 2s `ensureAutoPolling`；倒计时 timer 保留。  
- 回退时恢复原轮询间隔（Job 按 action；Auto 2s）。

### 9.4 完成逻辑单路径

抽取「终态 job 对象 → 完成处理」函数，供 terminal 事件与轮询共用，避免两套 toast。

### 9.5 多标签

每标签独立 EventSource；可接受。

### 9.6 兼容

不依赖构建工具；继续原生 `EventSource`（同源）。若需自定义头——v1 不需要。

---

## 10. 后端实现细节备忘

### 10.1 StreamingResponse 注意点

- 生成器内 `queue.get(timeout=…)` 以便插入心跳。  
- 捕获 `asyncio`/线程差异：若在同步路径用 `queue.Queue`，可用任意线程 publish + 同步生成器（Starlette 对 sync generator 会线程池执行——注意别阻塞整个进程过久；timeout 短循环即可）。  
- 备选：`asyncio.Queue` + async 生成器；则 hub publish 需 `loop.call_soon_threadsafe`。  
- **推荐实现选型（钉死一种）：**  
  - **方案 S（推荐）：** 同步 `queue.Queue` + 同步生成器 + `StreamingResponse`；简单，与现 Job 线程模型一致。  

### 10.2 CORS / 安全

本地同端口静态与 API，无额外 CORS。勿把 SSE 暴露到未受信网络而不加防护（产品本即本地）。

### 10.3 日志

hub 溢出丢弃打 **debug**；SSE 连接建立/断开打 **info**（带客户端可省略）。

---

## 11. 测试规范

### 11.1 `tests/test_event_hub.py`

| 用例 | 要点 |
|------|------|
| publish/subscribe | 订阅者按序收到 |
| 多订阅者 | 广播相同 seq |
| 溢出保 terminal | 灌满 progress 后 publish terminal，订阅方仍能拿到 terminal |
| 溢出保 fatal snapshot | 同上 |
| 最新 auto.log | 溢出后仍保留最后 log |
| unsubscribe | 不再投递 |

### 11.2 Runner / Scheduler 集成（可轻量）

| 用例 | 要点 |
|------|------|
| try_start 发出 created | mock hub |
| progress/log/terminal 顺序 | mock run_action |
| `_log` 发 auto.log | |
| fatal 强制 snapshot | |

### 11.3 路由烟测

| 用例 | 要点 |
|------|------|
| GET `/api/events` Content-Type | 含 `text/event-stream` |
| 首包含 snapshot | 读流前几 KB |

### 11.4 回归

既有 `test_job_runner_*`、`test_auto_scheduler_*`、`test_web_api.py` **全绿**；不因 import hub 破坏隔离库测试。

### 11.5 不测

- 浏览器 EventSource 真连（手测）  
- 多机 fan-out  

---

## 12. 实现分期

| 阶段 | 交付 | 验收 |
|------|------|------|
| **P1** | `event_hub.py` + 单测溢出策略 | pytest hub |
| **P2** | JobRunner 全量 publish | mock 断言事件 |
| **P3** | AutoScheduler publish + 节流 | fatal/log 事件 |
| **P4** | `GET /api/events` + 心跳 | 烟测 Content-Type/首帧 |
| **P5** | `app.js` SSE + H2 回退；完成逻辑单路径 | §13 手测 |
| **P6** | 全量 pytest + 文档状态更新 | 309+ 绿 |

---

## 13. 手测验收清单

环境：重启 `run_dashboard.py` 加载新代码。

### Job

- [ ] 一键更新：进度条/日志坞近实时，无明显 1s 一顿的「轮询感」  
- [ ] 三连/单参与：步骤与终态结果正常  
- [ ] 登录：二维码出现与自动刷新；成功；取消 → cancelled  
- [ ] 取消运行中任务：UI 恢复，toast 合理  
- [ ] DevTools → `/api/events` 为 event-stream，可见 `job.*`  

### 回退

- [ ] 人为断开 SSE（停后端再启 / 或临时改错 URL）：自动回到轮询，任务仍能跑完并刷新列表  
- [ ] SSE 恢复后可再次以推送为主（若实现重试）  

### Auto（B2）

- [ ] 启动调度：面板 phase / next / pipeline 实时更新；不必等 2s  
- [ ] 调度日志逐行出现  
- [ ] 撞车 fatal：面板立即显示停机原因  
- [ ] 停止调度：状态立刻 stopped  
- [ ] SSE 失败时恢复 2s 轮询，面板仍可用  
- [ ] 倒计时秒数连续（本地 timer）  

### 共存

- [ ] `GET /api/jobs/current`、`GET /api/auto/status` 仍返回合理 JSON  
- [ ] 两标签页同时打开均可看到同一任务/调度更新  

### 语义

- [ ] 调度仍不 cancel 业务任务；撞车仍 fatal  

---

## 14. 风险与对策

| 风险 | 对策 |
|------|------|
| sync 生成器阻塞线程池 | queue.get 短超时 + 心跳循环 |
| 双通道（SSE+轮询）重复 toast | 互斥启停；完成逻辑加 job id 去重 |
| auto.snapshot 过大 | logs≤30；节流 500ms |
| 登录二维码不刷新 | progress 必须带 `qrcode_refreshed_at` |
| 测试污染 | hub 可重置；isolated_home 测试不依赖真实 SSE 长连 |
| EventSource 不触发 comment | 使用 `heartbeat` 事件而非仅 comment |

---

## 15. 编码检查表（PR 自检）

- [ ] 仅 `/api/events` 一条 SSE，无 WS  
- [ ] current / auto/status 未删  
- [ ] Job 事件名与方向三一致  
- [ ] job.log 为 chunk；非每次全量  
- [ ] auto.log 增量 + snapshot 节流  
- [ ] 溢出不丢 terminal；fatal snapshot 可保  
- [ ] publish 永不抛到业务线程  
- [ ] 前端 H2 回退；完成逻辑不双份  
- [ ] 倒计时不靠每秒推送  
- [ ] 相关 pytest 全绿  

---

## 16. 文档关系

| 文档 | 职责 |
|------|------|
| [02-realtime-progress.md](./02-realtime-progress.md) | 拍板结论 |
| **本文** | 编码级规范 |
| [03-backend-task-model-impl.md](./03-backend-task-model-impl.md) | Job 语义与钩子点 |
| [fullstack-roadmap.md](../fullstack-roadmap.md) §2 | 总览状态 |

---

## 17. 状态

| 项 | 状态 |
|----|------|
| 拍板 A–H + 边角 | ✅ |
| 本文规范 | ✅ 成文 |
| 编码 P1–P6 | ✅ |
| 验收 | ⏳ 建议按 §13 手测；相关 pytest 已绿 |
