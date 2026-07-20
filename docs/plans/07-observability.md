# 方向七：可观测性 — 拍板记录与设计想法

> 状态：**已拍板**；落地实现规范见 [07-observability-impl.md](./07-observability-impl.md)  
> 关联：[全栈路线图 §7](../fullstack-roadmap.md)、[方向一 数据层](./01-sqlite-data-layer.md)、[方向二 SSE](./02-realtime-progress.md)、[方向三 任务模型](./03-backend-task-model.md)、[方向四 API 契约](./04-api-contract.md)、[方向六 测试](./06-testing-quality.md)  
> 更新：2026-07-20

本文记录两件事：

1. **拍板结论**（产品/工程边界，已定）  
2. **设计想法**（对照现有 `binggo.log`、JobRunner、SSE、任务日志坞的取舍）

---

## 0. 总前提（已对齐）

| 前提 | 含义 |
|------|------|
| 本地单机控制台 | 排查的是本机一次任务 / 一次调度；**不上** ELK、Prometheus、云 APM |
| 底座已有 | 方向一 `jobs` 表、方向二 SSE、方向三 JobRunner、方向四错误码已落地；本方向**不改** Job 状态机与 SSE 事件名 |
| 文件日志仍是完整轨迹 | 与方向三约定一致：DB `log_summary` 仍截断；**完整轨迹以日志文件为准** |
| UI 任务日志坞保留 | `#log-dock` / `job.log` SSE **不撤不换**；本方向补的是「可按 job 检索的结构化落盘 + 诊断」 |
| 不污染业务语义 | 默认日志级别、热路径耗时埋点须克制；禁止为埋点在持锁时打网 |
| 密钥不进明文诊断 | Cookie / LLM Key 等须脱敏；诊断包默认脱敏 |

---

## 1. 现状摘要（拍板依据）

### 1.1 已有能力

| 层 | 现状 | 路径 |
|----|------|------|
| 文件日志 | 纯文本 `RotatingFileHandler`，5MB×5；格式 `时间 [LEVEL] name: message` | `src/app_logging.py` → `{DATA_DIR}/logs/binggo.log` |
| Job 串联（弱） | `logger.info("任务启动 job_id=%s …")` 把 id **写进字符串**，无结构化字段 | `web/job_runner.py` 等 |
| SSE / EventHub | `job.created/progress/log/terminal` 等 dict 已含 `id`/`ts`/`seq` | `web/event_hub.py`、`web/sse.py` |
| DB | `jobs.log_summary` 末 16KB；历史行有 `action/state/source` | `src/job_store.py`、方向三 |
| 前端 | 「任务日志」坞展示**当前任务**内存/SSE 日志；**无**读磁盘日志 API | `web/frontend` `#log-dock` |
| 诊断导出 | **无** | — |

### 1.2 真实痛点

| 痛点 | 表现 |
|------|------|
| 难按一次任务过滤 | `grep job_id=42` 脆；无统一字段，子模块日志常不带 id |
| 多源耗时不可比 | 一键更新跨 DS1–6 / 流水线阶段，缺少统一 `duration_ms` / `phase` |
| 求助成本高 | 用户/开发者只能整份甩 `binggo.log`，含噪声与潜在敏感片段 |
| 文本与 SSE 两套真相 | 控制台坞是任务用户文案；文件是工程日志——合理，但文件侧未结构化 |

### 1.3 与既有拍板的边界（勿越界）

| 已有结论 | 对本方向的约束 |
|----------|----------------|
| 方向一：`data/logs/binggo.log` **保持文件、不进库作主存储** | v1 **不以**「全量日志进 SQLite」替代文件 |
| 方向二：非目标含「替换文件日志」 | SSE 继续服务 UI；文件结构化是另一条线 |
| 方向三：完整日志以文件为准；DB 仅摘要 | 保持；不作第二套全文库 |

---

## 2. 拍板结论一览（已定）

| 编号 | 议题 | 结论 | 说明 |
|------|------|------|------|
| **A** | 落盘形态 | **A1** | 仅 JSON Lines 文件；不加全量事件表 |
| **B** | 文件格式 | **B1** | 文件全面 JSONL（控制台人话见 H） |
| **C** | 字段契约 | **C2** | 必填 + 条件字段（见 §3） |
| **D** | job 上下文绑定 | **D1** | `contextvars` 自动注入 |
| **E** | 耗时埋点范围 | **E2** | job + 各 DS + 流水线阶段 |
| **F** | 查询入口 | **F2** | 只读过滤 API（`internal`） |
| **G** | 诊断包 | **G2** | 控制台「导出诊断包」（脱敏） |
| **H** | 控制台输出 | **H2** | 开发人话、文件 JSONL |
| **I** | 脱敏 | **I1** | formatter 写入时统一脱敏 |
| **J** | 与 UI 日志坞 | **J1** | 正交不合并 |
| **K** | 调度日志 | **K1** | 同一文件、同一契约（`component=auto`） |

### 边角（已定）

| 编号 | 议题 | 结论 |
|------|------|------|
| **①** | 轮转 / 文件名 | 保持 **5MB × 5**；**文件名仍为 `binggo.log`，内容改为 JSONL**（impl 钉死） |
| **②** | 过滤 API 窗口 | 当前文件 + 最近 1 个备份；单次最多 **500** 行 |
| **③** | 级别 | 默认 INFO；span INFO；高频 progress **不**落盘 |
| **④** | 行版本 | 每行 `v: 1` |
| **⑤** | 前端入口 | 概览项目展示区次要按钮；不做日志大屏 |
| **⑥** | 测试 | pytest 为主；不强制 E2E 点诊断 |
| **⑦** | 与方向八 | 脱敏清单可复用；本方向不做密钥加密 |

---

## 3. 拍板 C / D / E 展开（字段与串联）

### 3.1 字段契约（C2）

**每一行始终有：** `v`, `ts`, `level`, `logger`, `msg`  

**Job 工作线程自动带上：** `job_id`, `action`, `job_source`  

**条件字段：** `component`, `source_id`, `phase`, `duration_ms`, `event`, `error_kind`, `extra`  

细则与示例见落地规范 §5。

### 3.2 D1 — `contextvars`

- `JobRunner._run_worker` 入口绑定，结束重置。  
- `refresh_all` 线程池须 `copy_context().run`（详见 impl §6.3）。  
- 非 Job 路径省略 `job_id` 键。

### 3.3 E2 — 耗时埋点

**要埋：** Job 起止；各 DS；流水线 classify/detail/persist；可选 watch/status 整段。  
**不埋：** 每个 `job.progress`；每条活动；持锁打网。

---

## 4. 拍板取舍摘要

| 拍板 | 选 | 不选（及原因） |
|------|----|----------------|
| **A1** | JSONL 文件为主 | A2 全量进 SQLite：与方向一冲突且膨胀；A3 span 表留二期 |
| **B1** | 文件全面 JSONL | B2 双写浪费；B3 无法稳定过滤 |
| **F2** | 只读过滤 API | F1 对装包用户不友好；F3 调试站超范围 |
| **G2** | 控制台导出诊断包 | G1 痛点仍在；G3 仅 CLI 不够 |
| **H2** | 文件 JSONL + 控制台人话 | H1 控制台难读 |
| **I1** | 写入时脱敏 | 避免文件已留明文 |
| **J1** | 与任务日志坞正交 | J2 搅浑用户文案与工程日志 |
| **K1** | 调度同一文件 | K2 多文件增加成本 |

### 4.1 API 形状（已定）

```text
GET /api/diagnostics/logs?job_id=&limit=
GET /api/diagnostics/bundle?job_id=
```

- `tags=["internal"]`，`include_in_schema=False`  
- 不要求登录；包内不含 Cookie 明文  
- bundle 成功体为 JSON：`{ ok, filename, text }`（前端复制 + 下载）

---

## 5. 目标形态

```text
JobRunner / actions / DS / pipeline
        │
        ▼
 contextvars(job_id, action, …)  +  log_span(...)
        │
        ▼
 binggo logger ──JSON Formatter(+脱敏)──► data/logs/binggo.log（JSONL，轮转）
        │
        ├─(开发 console=True)──► 控制台人话 Formatter
        │
        ▼
 GET /api/diagnostics/logs|bundle  ──► 概览「导出诊断包」
```

并行保留：SSE 任务日志坞 + `jobs.log_summary` 截断。

---

## 6. 设计想法（背景，供对照）

### 6.1 为何做方向七

排障仍停在纯文本；本地产品需要 `job_id` 贯穿与脱敏诊断包，而非空挂 Grafana。

### 6.2 为何不上 ELK / 全量 SQLite 日志

单机量级下 JSONL + 有界 API 已能回答「哪个 DS 慢/挂」。

### 6.3 与 SSE `job.log` 的分工

| 通道 | 受众 | 内容 |
|------|------|------|
| SSE / 日志坞 | 控制台用户 | 已消毒进度/结果文案 |
| JSONL 文件 | 开发者 / 诊断包 | logger、phase、耗时 |

### 6.4 分期（见 impl §15）

P1 格式与脱敏 → P2 span 埋点 → P3 API → P4 前端入口。

### 6.5 与其它方向

| 方向 | 关系 |
|------|------|
| 1 | 日志仍文件 |
| 2 / 3 | 复用 `job_id`；不改事件名 |
| 4 | diagnostics 统一错误体；internal |
| 6 | pytest 覆盖新模块 |
| 8 | 脱敏可衔接；加密不做 |
| 9 / 10 | 路径随 HOME；MCP 非本方向必做 |

---

## 7. 验收红线

见落地规范 [§16](./07-observability-impl.md)。摘要：

- JSONL 可按 `job_id` 过滤  
- DS/阶段有 `duration_ms`  
- 诊断包脱敏  
- 日志坞 / SSE 不回归  
- 无 ELK / 无全量日志表  

---

## 8. 非目标

- 分布式追踪、云日志、运维大屏  
- 用文件日志替换任务日志坞  
- 为覆盖率改写业务结构  

---

## 9. 状态

| 项 | 状态 |
|----|------|
| 总前提 | ✅ 已定 |
| 拍板 A–K | ✅ 全部按建议 |
| 边角 ①–⑦ | ✅ 已定（① 文件名仍 `binggo.log`） |
| 落地实现规范 | ✅ [07-observability-impl.md](./07-observability-impl.md) |
| 编码 | ✅ 已落地（P1–P4） |

讨论记录：

| 日期 | 内容 |
|------|------|
| 2026-07-20 | 初稿：给出 A–K 与边角建议供拍板 |
| 2026-07-20 | 用户确认：**全部按建议**；落地实现规范成文 |
| 2026-07-20 | P1–P4 编码完成：JSONL、contextvars、span、diagnostics API、前端导出 |
