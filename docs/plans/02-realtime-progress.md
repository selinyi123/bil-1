# 方向二：实时进度 — 拍板记录与设计想法

> 状态：**已拍板**；落地实现规范见 [02-realtime-progress-impl.md](./02-realtime-progress-impl.md)  
> 关联：[全栈路线图 §2](../fullstack-roadmap.md)、[方向三拍板](./03-backend-task-model.md) / [impl §11 JobEvent](./03-backend-task-model-impl.md)  
> 更新：2026-07-18

本文记录两件事：

1. **拍板结论**（产品/工程边界，已定）  
2. **设计想法**（对照现有轮询与已落地任务模型的取舍，供实现时对照）

---

## 0. 总前提（已对齐）

| 前提 | 含义 |
|------|------|
| 本地单机控制台 | 浏览器 ↔ 本机 FastAPI；**不上** Redis/Kafka/多机 fan-out |
| 方向一、三已落地 | 任务有稳定 `id` + 状态机 + `jobs` 落库；JobEvent 形状沿用方向三 H2 |
| 行为可感知不倒退 | 进度条、日志坞、登录二维码、终态提示、**调度监视面板**与现网一致或更好 |
| 轮询可作退路 | SSE 断线或失败时，Job 回退 `GET /api/jobs/current`；调度回退 `GET /api/auto/status`（H2） |
| 调度语义不变 | 自动调度仍 B1；启停/取消仍走现有 POST，**不**经 SSE 上行 |

---

## 1. 现状摘要（拍板依据）

### 1.1 现有链路

```text
Job 路径：
  JobRunner → 前端 startPolling → GET /api/jobs/current（400ms～1s）

调度路径：
  AutoScheduler → 前端 ensureAutoPolling → GET /api/auto/status（2s）
  + 本地 setInterval 1s 倒计时（不打后端）
```

| 模块 | 路径 | 与推送相关的现状 |
|------|------|------------------|
| Job 轮询 | `app.js` → `startPolling` | login 500ms；参与 400ms；其它 1s |
| 调度轮询 | `app.js` → `ensureAutoPolling` | 固定 2s 拉全量 status（含 logs、pipeline、next_slot） |
| 任务 API | `web/app.py` | `/api/jobs/*`、`/api/auto/*` |
| JobRunner | `web/job_runner.py` | 尚无事件 hub |
| 方向三约定 | impl §11 | `job.created/progress/log/terminal` |

### 1.2 真实痛点

| 痛点 | 表现 |
|------|------|
| Job 空转/延迟 | 运行中固定间隔 HTTP；进度/日志最多落后一个 poll 周期 |
| 调度面板空转 | 即便 idle 也可能 2s 拉一次全量（含 logs 数组） |
| 完成逻辑绑轮询 | UI 完成靠「发现非 running」驱动 |
| 两套轮询并存 | Job 与 Auto 各自打点，本方向一并收敛（你已选 B2） |

---

## 2. 拍板结论一览（已定）

| 编号 | 议题 | 结论 | 说明 |
|------|------|------|------|
| **A** | 传输协议 | **A1 SSE** | 不上 WebSocket |
| **B** | 推送范围 | **B2** | **Job 事件 + AutoScheduler 状态** 一并推 |
| **C** | 与 REST 共存 | **C2** | 保留 `GET /api/jobs/current` 作快照+回退 |
| **D** | 事件模型 | **D2** | Job 侧沿用方向三 JobEvent 名 |
| **E** | Job 日志形态 | **E2** | 增量 chunk + 重连/终态可 snapshot |
| **F** | 订阅模型 | **F2** | 进程级事件流（非仅订单个 job_id） |
| **G** | 断线/多订阅 | **同意** | 心跳 15s；多订阅者；有界队列丢旧保 terminal |
| **H** | 前端策略 | **H2** | SSE 优先；失败回退轮询 |

### 2.1 B2 含义（已写入前提）

> 控制台一条（或逻辑上统一的）实时流，既推任务进度，也推调度监视面板所需状态；REST 快照接口仍保留作首屏与回退。

调度启停、任务取消：**继续 POST**，不走 SSE 上行。

---

## 3. 拍板议题展开（归档）

### 3.1 A → **A1 SSE**

单向 `text/event-stream`；取消/启停仍 REST。

### 3.2 B → **B2 Job + Auto**

除 JobEvent 外，增加 Auto 侧事件（具体形态见 §8.1～§8.3）。  
`/api/auto/status` **保留**（对仗 C2 / H2），不作为热路径。

### 3.3 C → **C2**

首屏 / 重连 / SSE 失败：`GET /api/jobs/current`（及调度的 `GET /api/auto/status`）。

### 3.4 D → **D2 JobEvent**

| event | 要点 |
|-------|------|
| `job.created` | id, action, source, label |
| `job.progress` | id, step, total, message；建议带 `result` 片段（登录 phase/二维码） |
| `job.log` | id + chunk（E2） |
| `job.terminal` | id, state, message；可带最终 log |
| `job.snapshot`（建议） | 订阅时/重连对齐用 |

Auto 事件命名空间建议 `auto.*`（与 job 分开，见 §8）。

### 3.5 E → **E2**

Job 日志：增量 `chunk`；重连先拉 current 对齐。

### 3.6 F → **F2**

进程级流：打开控制台即可挂长连；有 Job/Auto 变更即推。

### 3.7 G → **同意**

心跳 15s；多标签多订阅；队列有界，溢出丢旧 progress/log，**不丢** `job.terminal` / 调度 `fatal` 类关键事件。

### 3.8 H → **H2**

Job：SSE 失败 → `startPolling`。  
Auto：SSE 失败 → 恢复 2s `ensureAutoPolling`。  
倒计时 UI 仍可用本地 1s timer（不必服务器每秒推 `server_now`）。

---

## 4. 建议目标形态（已按拍板收束）

一句话：

> **一条 SSE 进程流：JobEvent（D2/E2）+ Auto 状态推送（B2）；current/auto/status 作快照与 H2 回退；倒计时仍本地算。**

### 4.1 模块想象

```text
JobRunner.publish ──┐
                    ├──► EventHub ──► GET /api/events（或 /api/jobs/events）SSE
AutoScheduler.pub ──┘                      │
                                           ▼
                              app.js EventSource（H2 可回退双轮询）
```

### 4.2 非目标（本方向仍不做）

- WebSocket 双向协议  
- Redis / 跨进程总线  
- 鉴权 SSE token  
- 替换文件日志 `binggo.log`  
- 前端工程化大拆包（方向五）  

---

## 5. 设计想法（背景）

### 5.1 为何接受 B2

调度监视面板也是「长连接空转」重灾区（2s 全量）；与 Job 同 hub 广播，本地多一个发布点即可，避免控制台挂两条无关联长连（端点形态见 §8.1）。

### 5.2 倒计时不要每秒推

`next_slot.at_unix` 推一次，前端本地 `setInterval(1s)` 刷新文案即可；`server_now` 仅在 snapshot / 状态变更时带上做校准。

### 5.3 调度日志 vs Job 日志

调度 `logs` 是面板环形缓冲（约 80～200 条）；宜 **增量一行** 或 **变更时推裁剪后的尾部快照**，避免每次把整个数组塞进 SSE（见 §8.3）。

### 5.4 进度推送频率

Job：内存 progress 变更即可 publish（可比写库更勤）。  
Auto：`state/phase/pipeline/last_click/fatal` 变更时推；勿在 wait 循环里无节流狂推。

---

## 6. 拍板后建议回归范围

- [ ] Job：刷新/参与/三连/登录（含二维码刷新）实时  
- [ ] Job：取消、终态 toast/结果；断线回退轮询仍能结束  
- [ ] Auto：启动后面板 phase、pipeline、next 提示实时；fatal 立刻可见  
- [ ] Auto：停止/撞车停机文案正确；SSE 挂了回退 2s 轮询  
- [ ] 多标签页均可看 Job + Auto  
- [ ] REST：`/api/jobs/current`、`/api/auto/status`、cancel/start/stop 仍可用  
- [ ] 调度业务语义（不 cancel 业务、撞车 fatal）不变  

---

## 7. 实现分期想象（边角拍板后写入 impl）

| 阶段 | 交付 |
|------|------|
| P1 | EventHub + Job publish + 单测 |
| P2 | Auto publish（按 §8 形态） |
| P3 | SSE 端点 + 心跳 |
| P4 | 前端：Job + Auto 订阅；H2 双回退 |
| P5 | 手测 + pytest |

---

## 8. 边角拍板（已定：全按推荐）

| 编号 | 议题 | 结论 |
|------|------|------|
| **①** | SSE 端点 | **甲：一条流** `GET /api/events`（`job.*` + `auto.*`） |
| **②** | Auto 粒度 | **甲：变更时 `auto.snapshot`**（精简版 status；logs 可裁剪） |
| **③** | Auto 日志 | **甲：`auto.log` 增量**；重连拉 `/api/auto/status` |
| **④** | `/api/auto/status` | **甲：长期保留** |
| **⑤** | 队列溢出保底 | **甲：保 fatal/stopped 类 snapshot + 最新 auto.log**；Job 保 terminal |

### 8.1 默认可由实现者定（已写入 impl）

| 项 | 默认倾向 |
|----|----------|
| 心跳 | 15s |
| 队列深度 | 256 |
| Job progress 带 result 片段 | 登录相关要带 |
| 倒计时 | 前端本地 1s |
| `Last-Event-ID` | v1 不做；重连靠 REST |
| hub 模块 | `web/event_hub.py` |

---

## 9. 文档关系

| 文档 | 职责 |
|------|------|
| [fullstack-roadmap.md](../fullstack-roadmap.md) §2 | 总览 |
| **本文** | 拍板边界与设计想法 |
| `02-realtime-progress-impl.md`（待写） | 编码级规范 |
| [03-backend-task-model-impl.md](./03-backend-task-model-impl.md) §11 | JobEvent 来源 |

---

## 10. 状态

| 项 | 状态 |
|----|------|
| 现状梳理 | ✅ |
| 拍板 A–H | ✅ 已定（见 §2；含 B2） |
| 边角 ①～⑤ | ✅ 全按推荐 |
| 落地实现规范 | ✅ [02-realtime-progress-impl.md](./02-realtime-progress-impl.md) |
| 编码 | ✅ 已按 impl 落地 |

讨论记录：

| 日期 | 内容 |
|------|------|
| 2026-07-18 | 初稿建议 B1 |
| 2026-07-18 | 拍板：A1、B2、C2、D2、E2、F2、G 同意、H2 |
| 2026-07-18 | 边角全按推荐；成文 impl |
