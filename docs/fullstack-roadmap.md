# Binggo 全栈深化路线图（讨论稿）

> 状态：方向 1–9 **已落地**；方向 10（Skill / MCP）待讨论  
> 目的：把「真实需求 → 技术选型 → 边界」记清楚，避免为简历硬堆栈  
> 更新：2026-07-20

本文记录十个全栈方向，供后续逐个评审后再开工。原则：

1. **场景先于技术**：写不清「现在卡在哪」的方向，不进入实现。
2. **本地单机优先**：不过度引入 Kafka / K8s 等与产品形态不符的组件。
3. **不另开仓库**：能力长在本项目内；LLM 只作为业务模块，不做「对话点按钮」式 Agent。
4. **可写进简历**：每项都能对应可验证的 GitHub 改动与面试话术。

---

## 总览

| # | 方向 | 一句话目标 | 建议优先级 | 状态 |
|---|------|------------|------------|------|
| 1 | 数据层 | JSON 文件 → 本地数据库 | P0 | 已完成（`binggo.db` + `scripts/import_json_to_db.py`；见 plans/01） |
| 2 | 实时进度 | 轮询 → 推送 | P0 | 已落地（见 [plans/02-realtime-progress-impl.md](./plans/02-realtime-progress-impl.md)） |
| 3 | 后端任务模型 | 进程内线程 → 清晰任务抽象 | P0 | 已落地（见 [plans/03-backend-task-model-impl.md](./plans/03-backend-task-model-impl.md)） |
| 4 | API 层 | 脚本式接口 → 稳定后端契约 | P1 | 已落地（见 [plans/04-api-contract-impl.md](./plans/04-api-contract-impl.md)） |
| 5 | 前端工程化 | 单文件脚本 → 可维护前端 | P1 | 已落地（见 [plans/05-frontend-engineering.md](./plans/05-frontend-engineering.md) / [impl](./plans/05-frontend-engineering-impl.md)） |
| 6 | 测试与质量 | 单测为主 → 关键路径自动化 | P1 | 已落地（见 [plans/06-testing-quality.md](./plans/06-testing-quality.md) / [impl](./plans/06-testing-quality-impl.md)） |
| 7 | 可观测性 | 日志文件 → 结构化可查 | P1 | 已落地（见 [plans/07-observability.md](./plans/07-observability.md) / [impl](./plans/07-observability-impl.md)） |
| 8 | 配置与安全 | 本地密钥与配置治理 | P1～P2 | 已落地（见 [plans/08-config-security.md](./plans/08-config-security.md) / [impl](./plans/08-config-security-impl.md)） |
| 9 | 分发与安装 | 打包 / 发布 / 升级体验（含 macOS） | P2 | 已落地（见 [plans/09-distribution.md](./plans/09-distribution.md) / [impl](./plans/09-distribution-impl.md)） |
| 10 | 拓展：Skill / MCP | 把能力暴露给外部 Agent | P2～探索 | 待讨论 |

建议暑期主线顺序：**1 → 3 → 2**（数据与任务底座先稳，再推送），其余按讨论结果穿插。

---

## 1. 数据层：JSON 文件 → 真正的本地数据库

### 真实需求 / 痛点

- 活动库、参与记录等以 JSON 文件为主；并行写曾出现 Windows 权限冲突。
- 复杂筛选、统计、后续语义检索都受文件结构限制。
- 缺少迁移、索引、事务语义，演进成本高。

### 目标形态

- 本地 **SQLite**（或 SQLModel/SQLAlchemy）作为主存储。
- 表结构覆盖：活动、参与、数据源检查点、任务状态（可与方向 3 共用）等。
- **迁移工具**（如 Alembic）管理 schema 变更；关键字段建索引。

### 候选技术

- SQLite + SQLAlchemy/SQLModel  
- 启动时自动迁移；保留「导出 JSON」作备份/调试（可选）

### 非目标

- 上云数据库、多租户、读写分离。

### 讨论清单

- [x] 进库范围、切换策略、统计/JSON 列/ORM/jobs/导入 — 已拍板（见方案文档）
- [ ] 表结构 DDL 与导入脚本幂等策略（实现前钉死）
- [ ] 编码切换与回归验收

### 方案文档

→ [plans/01-sqlite-data-layer.md](./plans/01-sqlite-data-layer.md)（拍板记录 + 设计想法）  
→ [plans/01-sqlite-data-layer-impl.md](./plans/01-sqlite-data-layer-impl.md)（**写码前落地规范**：表结构、Store、导入、测试、切换）

### 简历可写点（草案）

> 将活动与参与数据从 JSON 文件迁移至 SQLite，以事务与索引支撑并发参与和复杂筛选。

---

## 2. 实时进度：轮询 → 推送

### 真实需求 / 痛点

- 前端对任务状态轮询，延迟与空转并存，日志坞/进度条偶发不同步感。
- 长任务（一键更新、三连、状态刷新）更适合服务端推送事件。

### 目标形态

- 任务进度、日志行、完成/失败事件经 **SSE**（优先，实现简单）或 **WebSocket** 推到控制台。
- 前端订阅单一任务流；断线可回退到「拉一次全量状态」。

### 候选技术

- FastAPI `StreamingResponse` / SSE  
- 或 WebSocket（若后续要双向控制指令再上）

### 非目标

- 分布式消息总线；多客户端同步协作。

### 讨论清单

- [ ] SSE 与现有 `JobRunner.get_status` 如何共存？（见方案 C）
- [ ] 日志是「逐行 push」还是「快照 + 增量」？（见方案 E）
- [ ] 与方向 3 的任务事件模型是否共用一套事件类型？（见方案 D）

### 方案文档

→ [plans/02-realtime-progress.md](./plans/02-realtime-progress.md)（拍板）  
→ [plans/02-realtime-progress-impl.md](./plans/02-realtime-progress-impl.md)（落地实现规范；已编码）

### 简历可写点（草案）

> 长任务进度与日志改为 SSE 实时推送，替代轮询。

---

## 3. 后端任务模型：进程内线程 → 清晰的任务抽象

### 真实需求 / 痛点

- 参与、刷新、定时调度等同进程竞争；互斥多靠约定。
- 任务状态偏内存，重启后难追溯；取消/完成语义需更清晰。

### 目标形态

- 明确的 **Job 状态机**（queued / running / success / error / cancelled）。
- 任务元数据可落库（依赖方向 1）；约束「同时仅一个业务任务」等规则可配置。
- 定时调度与抽奖任务的边界保持现有产品语义（调度不取消业务任务）。

### 候选技术

- 先：进程内队列 + 状态机 + SQLite 任务表  
- 后（仅当证明需要）：多进程 worker；**默认不上** Celery/Redis

### 非目标

- 集群调度、跨机器任务分发。

### 讨论清单

- [ ] `JobRunner` 与 `auto_scheduler` 的职责如何重新划界？（见方案 A/E/B）
- [ ] 哪些状态必须持久化？哪些仍可仅内存？（见方案 C）
- [ ] 取消令牌、超时、重试是否纳入 v1？（见方案 F）

### 方案文档

→ [plans/03-backend-task-model.md](./plans/03-backend-task-model.md)（拍板）  
→ [plans/03-backend-task-model-impl.md](./plans/03-backend-task-model-impl.md)（落地实现规范；已编码）

### 简历可写点（草案）

> 设计本地任务状态机与持久化任务表，统一编排参与/刷新/调度并保证互斥与可取消。

---

## 4. API 层：脚本式接口 → 稳定的后端契约

### 真实需求 / 痛点

- 接口可用，但请求/响应/错误形态不完全统一，前后端耦合紧。
- 后续若接 MCP、桌面以外客户端，需要稳定契约。

### 目标形态

- 统一 Pydantic 请求/响应模型与错误体（code / message / detail）。
- OpenAPI 即文档；写操作考虑幂等键（可选）。
- 版本策略简单即可（如 `/api/v1` 或文档约定兼容规则）。

### 候选技术

- FastAPI + Pydantic v2  
- 统一异常处理中间件

### 非目标

- 对外公网多租户 API、复杂 OAuth。

### 讨论清单

- [ ] 现有前端改动面有多大？是否分阶段兼容旧字段？（见方案 I）
- [ ] 哪些接口属于「内部调试」、哪些算正式契约？（见方案 D）
- [ ] 与方向 10（MCP）是否共用同一套 action 定义？（见方案 H）

### 方案文档

→ [plans/04-api-contract.md](./plans/04-api-contract.md)（拍板记录；**已全部按建议拍板**）  
→ [plans/04-api-contract-impl.md](./plans/04-api-contract-impl.md)（**写码前落地规范**：错误体、契约代、schema、端点、前端双读、测试分期）

### 简历可写点（草案）

> 整理本地控制台 REST 契约与统一错误模型，便于多客户端复用。

---

## 5. 前端工程化：单文件脚本 → 可维护前端

### 真实需求 / 痛点

- `web/static/app.js` 体量大，状态与 DOM 更新交织，改动风险高。
- 活动筛选、任务坞、主题/侧栏等模块需要更清晰边界。

### 目标形态

- **Vite + TypeScript** 模块化；或局部引入组件框架（Vue/React）重构高复杂页面。
- 保持现有视觉与交互，不以「重做 UI」为目标。
- 静态资源构建产物仍可由 FastAPI / 打包器正确托管。

### 候选技术

- Vite + TypeScript（推荐作为默认讨论基线）  
- 可选：Vue 3 / React（仅当模块化仍不够时）

### 非目标

- SSR、微前端、大型全局状态中台。

### 讨论清单

- [ ] 全量 TS 迁移还是「新代码 TS、旧代码渐进」？（见方案 B）
- [ ] 构建产物目录与 `packaging/windows` 如何衔接？（见方案 D / I）
- [ ] 是否与方向 2 的 SSE 客户端一并模块化？（见方案 K）

### 方案文档

→ [plans/05-frontend-engineering.md](./plans/05-frontend-engineering.md)（拍板记录；**已全部按建议拍板**；设计零改动）  
→ [plans/05-frontend-engineering-impl.md](./plans/05-frontend-engineering-impl.md)（**已落地**：设计冻结、Vite/TS、模块拆分、FastAPI dist、打包 CI）

### 简历可写点（草案）

> 将控制台前端模块化（TypeScript），降低复杂交互的维护成本。

---

## 6. 测试与质量：单测为主 → 关键路径自动化

### 真实需求 / 痛点

- 后端 pytest 已有基础；UI 与主用户路径仍偏手测。
- 全栈改动（数据层/推送/前端）需要防回归网。

### 目标形态

- 保持并加强 API/领域单测与集成测。
- 增加 **Playwright**（或同类）冒烟：打开控制台、筛选活动、触发任务（登录可 mock）。
- CI（GitHub Actions）在 PR/push 时跑关键套件。

### 候选技术

- pytest（已有）  
- Playwright  
- 现有 Actions 工作流扩展

### 非目标

- 追求百分百 UI 覆盖；不稳定的全链路真登录 E2E。

### 讨论清单

- [x] 首批冒烟路径、数据隔离、CI 形态 — 已拍板
- [x] 落地实现规范成文
- [x] 按 impl 编码（P1–P5）

### 方案文档

→ [plans/06-testing-quality.md](./plans/06-testing-quality.md)（拍板记录；**已全部按建议拍板**）  
→ [plans/06-testing-quality-impl.md](./plans/06-testing-quality-impl.md)（落地规范；**P1–P5 已落地**）

### 简历可写点（草案）

> 为关键控制台路径补充自动化测试并接入 CI。

---

## 7. 可观测性：print/日志文件 → 结构化可查

### 真实需求 / 痛点

- 问题排查依赖文本日志，难按一次任务串联。
- 多数据源耗时、失败点缺少统一维度。

### 目标形态

- 结构化日志（JSON 行或等价），字段含 `job_id` / `action` / `source_id` 等。
- 一次「一键更新」可从日志或简易调试页按 job 过滤。
- 关键步骤耗时埋点（各 DS、流水线阶段）。

### 候选技术

- Python `logging` + JSON formatter  
- 可选：简易「最近 N 条任务事件」查询 API（依赖方向 1/3）

### 非目标

- 上完整 ELK / Prometheus + Grafana（除非后续真有运维需求）。

### 讨论清单

- [x] 日志仍落文件还是另增 sqlite 事件表 — **A1** 仅 JSONL 文件
- [x] 每行必带字段 — **C2**
- [x] 是否暴露脱敏诊断包 — **G2**
- [x] 落地实现规范成文
- [x] 按 impl 编码（P1–P4）

### 方案文档

→ [plans/07-observability.md](./plans/07-observability.md)（拍板记录；**已全部按建议拍板**）  
→ [plans/07-observability-impl.md](./plans/07-observability-impl.md)（落地规范；**P1–P4 已落地**）

### 简历可写点（草案）

> 引入请求/任务级结构化日志，支持按 job 追踪多源刷新耗时与失败点。

---

## 8. 配置与安全（本地产品向）

### 真实需求 / 痛点

- Cookie、LLM API Key 等敏感信息仅存本地，需防止误提交与错误权限。
- 配置项增多后缺少 schema 校验与安全默认值。

### 目标形态

- 配置 schema 校验；敏感字段明确清单与存储约定。
- 可选：密钥本地加密（DPAPI / keyring 等，按平台讨论）。
- 文档明确：数据目录、便携模式、卸载保留策略（已有部分可加强）。

### 候选技术

- Pydantic Settings  
- `keyring` / Windows DPAPI（可选）  
- 强化 `.gitignore` 与启动自检

### 非目标

- 账号体系、云端同步密钥。

### 讨论清单

- [x] 加密是否值得做进 v1，还是先做「检测明文 + 权限提示」？→ 见 [08-config-security.md](./plans/08-config-security.md) 议题 A（建议 A1）
- [x] 便携版与安装版路径策略是否要再简化？→ 见同文档议题 E（建议 E1）
- [x] 日志/诊断包如何脱敏？→ **方向七已落地**；方向八做清单对齐（议题 F/H）

拍板稿：[plans/08-config-security.md](./plans/08-config-security.md)  
落地规范：[plans/08-config-security-impl.md](./plans/08-config-security-impl.md)（**P1–P3 已落地**）

### 简历可写点（草案）

> 治理本地敏感配置与数据目录隔离，降低凭证泄漏与误提交风险。

---

## 9. 分发与安装

### 真实需求 / 痛点

- 已有 PyInstaller + Inno Setup + Release Actions，具备桌面分发能力。
- 可加强：升级体验、失败可诊断、版本可见性。

### 目标形态

- 保持 Setup / Portable 双产物。
- 可选：应用内检查更新（读 GitHub Releases）。
- 安装包/关于页展示版本号与数据目录说明（部分已有）。

### 候选技术

- 现有 `packaging/windows` + `release-windows.yml`  
- 可选：更新检查 API 客户端

### 非目标

- 应用商店上架、自动静默强更、代码签名商业证书（除非后续正式发布需要）。

### 讨论清单

- [x] 是否做应用内「检查更新」？→ 见 [09-distribution.md](./plans/09-distribution.md) 议题 B（建议 B2）
- [x] 崩溃日志是否本地汇总（无上报 / 可选上报）？→ 见同文档议题 D（建议 D1 复用诊断）
- [x] 版本号单一来源如何继续保持？→ 见同文档议题 A（建议 A1）

拍板稿：[plans/09-distribution.md](./plans/09-distribution.md)  
落地规范：[plans/09-distribution-impl.md](./plans/09-distribution-impl.md)（**待编码**；含 macOS arm64）

### 简历可写点（草案）

> 维护 Windows 安装包与便携版的 CI 发布流水线，完善升级与版本可见性。

---

## 10. 拓展：写成 Skill、MCP

### 真实需求 / 痛点

- 控制台能力（刷新某源、查未参加、参与等）若能以标准协议暴露，可被 Cursor 等外部 Agent 复用。
- 这是「拓展集成」，不是替代本机 UI；**不**等于在产品内做对话点按钮。

### 目标形态

- 将稳定 action 封装为 **MCP tools**（或 Agent Skill 说明 + 调用约定）。
- 工具输入输出与方向 4 的 API 契约对齐；危险操作强制确认或 deny-by-default。
- 文档说明：仅本机、需用户已登录、权限边界。

### 候选技术

- MCP Python SDK / 标准 IO 或本地 HTTP  
- Cursor Skill（`SKILL.md`）描述何时调用哪些工具  
- 复用现有 `web/actions.py` 能力，避免两套业务逻辑

### 非目标

- 公网 MCP；让模型绕过安全确认直接三连；用 MCP 取代 Web UI。

### 讨论清单

- [ ] 首批暴露哪些 tools？哪些永久不暴露？
- [ ] 与方向 4 是否要求「先有稳定 API 再包 MCP」？
- [ ] Skill 文档与 MCP server 是否同仓维护？
- [ ] 本地鉴权：如何防止任意本机进程滥用？

### 简历可写点（草案）

> 将抽奖控制台能力以 MCP/Skill 形式暴露为可编排工具，供外部 Agent 在明确权限下调用。

---

## 与大模型能力的关系（备忘）

全栈方向是主轴。LLM 仅在**业务真实需要**时接入，例如：

- 转发抽奖正文 → 结构化字段（已有，可加深校验与 Eval）
- 不在本路线图内单独立项「对话式操作面板」

LLM 相关加深若启动，应挂在方向 1/3/4 的服务边界上（抽取作为后端模块），而不是方向 10 的聊天产品化。

---

## 后续工作方式

1. **逐项讨论**：每次只拍板 1 个方向的范围、非目标、验收标准。  
2. **再写实现方案**：可另开短文（如 `docs/plans/01-sqlite.md`）或直接开 PR。  
3. **验收**：功能可用 + 测试/文档/版本说明同步；简历 bullet 用事实改写草案。  
4. **状态更新**：把上表「状态」改为：讨论中 / 方案已定 / 实现中 / 已完成。

### 讨论记录（预留）

| 日期 | 方向 | 结论 | 备注 |
|------|------|------|------|
| 2026-07-20 | 8 配置与安全 | 全部按建议拍板；P1–P3 已落地 | [08](./plans/08-config-security.md) / [impl](./plans/08-config-security-impl.md) |
| 2026-07-20 | 9 分发与安装 | 按建议 + macOS arm64；P1–P4 已落地 | [09](./plans/09-distribution.md) / [impl](./plans/09-distribution-impl.md) |

---

## 相关文档

- [Windows 打包说明](../packaging/windows/README.md)
- [macOS 打包说明](../packaging/macos/README.md)
- [活动流水线设计](./pipeline-redesign.md)
- [CLI 手册](./cli.md)
- [实现计划（历史）](./implementation-plan.md)
