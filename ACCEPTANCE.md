# Binggo 验收标准（ACCEPTANCE）

> 交接文档（2026-08）。验收覆盖构建、测试、功能、安全/不变量、发布与文档一致性。
> 每次改动（尤其涉及身份/参与/清理/凭据/数据源）必须通过对应不变量验收。
> 审计状态（A-01~C-07 及其关闭条件）唯一来源：`docs/14-全量逐函数与漏洞审计-2026-08-12.md`；本文件不复制审计寄存器。

> 验收等级：
> - **REQUIRED**：违反则不能合并/发布。
> - **REQUIRED-WHEN-TOUCHED**：仅当改动触及对应子系统时阻断合入；未触及时不适用。
> - **ADVISORY**：记录风险，可附 justification 合并。
>
> 没有执行的命令必须标记“未验证”，不得用历史结果代替本次证据。开发环境与历史踩坑见 `docs/development.md`，不属于验收标准。

## 1. 构建验收

| # | 检查项 | 命令/路径 |
|---|---|---|
| B1 | 后端可导入、无语法错误 | `python -m pytest tests/ -q` 收集成功 |
| B2 | 前端类型检查 + 构建通过 | `cd web/frontend && npm ci && npm run build`（vite build + tsc --noEmit） |
| B3 | 前端产物存在 | `web/static/dist/index.html` |
| B4 | PyInstaller 打包成功 | `powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1` → `dist/Binggo/Binggo.exe` |
| B5 | 安装包/便携包产物 | `dist/Binggo-Setup-win64.exe`、`dist/Binggo-Portable-win64.zip`（版本号与 `src/app_paths.__version__` 一致） |
| B6 | 打包版启动可用 | 双击/`Start-Process` 后 `http://127.0.0.1:8181` 返回 200，进程持续（launcher + serve） |

## 2. 测试验收

| # | 检查项 | 阈值 |
|---|---|---|
| T1 | 全量 pytest | 当前适用测试集合不得出现 unexpected failure（不设固定数量门槛；历史数字作为审计证据见 docs/14 §6） |
| T2 | 改动模块的聚焦测试 | 相关测试文件全绿 |
| T3 | 不变量测试覆盖 | 见 §4 清单，每个不变量必须有对应测试用例 |
| T4 | 前端 e2e（契约） | `web/frontend` 下 Playwright smoke / frontend-contract 通过（CI 执行） |

## 3. 功能验收（核心路径）

| # | 场景 | 预期 |
|---|---|---|
| F1 | 扫码登录 → 账号池登记 | `accounts/{uid}.txt` 生成、active 指向该 uid、UI 显示与实际请求身份一致 |
| F2 | BILI_COOKIE env 存在时 | 切号被拒（明确提示）、logout 返回明确错误、扫码仅登记不切换 |
| F3 | 参与活动 | actions 记录完整；repost 成功记录 `extra.created_dynamic_id`；participations/activities 三表一致（单事务） |
| F4 | `dry_run=true` 参与 | **零副作用**：不调用写接口、不持久化、活动库 joined 不变、返回"将执行"清单 |
| F5 | 三连参与 | 内部失败 → job `error`（`error_kind=business_partial`），`result.partial_failure` 含已完成活动与已开始动作；用户取消 → `cancelled` |
| F6 | 一键更新 refresh_all | 全部源失败 → `ok=False`；部分失败 → 消息明示；内容未变不触发流水线 |
| F7 | 清理 clear_follows | 默认预演；只删 `created_dynamic_id` 匹配的转发；手动转发不删；白名单保护；实时收缩分页全量处理且不死循环（回归场景规模见 docs/14 A-01） |
| F8 | 中奖深检 | 至少一渠道送达后才 mark DM read；全部失败保留未读；`delivered`/`acknowledged` 准确 |
| F9 | 数据源管理（Web） | DS-8/9 typed 保存；DS-10 脱敏增删；file:// 仅限 BINGGO_HOME；Job 运行中 mutation 被拒 |
| F10 | 通知 | 仅 HTTP 2xx 且业务码通过才记"已发送"；3xx/业务码异常不记 sent；飞书签名官方算法；配置凭据不回显 |
| F11 | 调度重启 | `stop()` 后旧 Scheduler generation 不再写状态/投递；快速 stop→start 同时最多一个 loop |
| F12 | Web mutation | Job 运行中 mutation 默认返回 JOB_BUSY（当前实现为全量 fail-closed）；取消等安全例外必须显式白名单并有测试；按资源冲突收窄的演进见 I18 |
| F13 | 任务寻址 | MCP 启动任务后只等待/返回该 `job_id`，连续同 action 任务不串号 |
| F14 | 导入一致性 | DS/WATCH 快照失败时核心导入不留下无标记提交；失败可重试或显式 `partial_commit` |
| F15 | DS-10 网络边界 | 默认拒绝 loopback/private/link-local/multicast/unspecified 和重定向私网；异常不含原始 URL |
| F16 | 发布入口 | update API、前端 Release、installer、测试全部指向 `selinyi123/bil-1` |
| F17 | 维护/安装归属 | 脚本默认 dry-run；installer 只终止本安装实例；launcher 用 runtime/contract/version 识别服务 |
| F18 | Job 账号绑定 | UI/auto 创建的非 login Job 持久化服务端 `account_uid`；执行前 UID 不一致时以 `error_kind=identity` 失败，且不调用 `run_action`；历史任务保持 NULL |

## 4. 安全与不变量验收（来自历轮 review，必须始终成立）

| # | 不变量 | 说明 |
|---|---|---|
| I1 | **清理 ownership** | Binggo 绝不删除非 Binggo 创建的动态；删除前归属校验（created id 精确 / 旧记录源 id 兼容）；默认 dry_run |
| I2 | **凭据不泄露** | 任意 GET/PUT/logs/diagnostics 永不返回真实 secret（含 bot_token/pass/push）；`notify.json` secret 权限写盘 |
| I3 | **身份一致** | UI active uid = HTTP Cookie uid = participation uid = job uid（`resolve_effective_uid` 单一真相源） |
| I4 | **取消语义** | 只有用户取消才产生 `cancelled`；内部业务失败终态 `error`（`business_partial` 不污染 internal 统计） |
| I5 | **部分副作用可追溯** | 失败 job 必须精确记录已执行动作（completed + partial:true） |
| I6 | **源健康** | 全部数据源失败永不返回 success；DS-10 全失败显式抛错 |
| I7 | **schema 兼容** | 未来版本 DB 在任何写操作前 hard fail；绝不自动降级回写；meta 行丢失 fail-closed |
| I8 | **通知确认** | provider 未确认成功（非 2xx、业务码失败/无法解析）绝不进入 `sent` |
| I9 | **dry_run 贯穿** | HTTP `dry_run=true` 必须传到底层；预演零副作用：不执行外部参与写操作、不写参与状态、不改变活动库 joined 状态 |
| I10 | **读函数无写副作用** | 读路径函数不得写库；seed/过期状态更新走显式函数 |
| I11 | **事务原子** | 参与结果三表（actions/participations/activities）同一事务；crash 不产生"已参加"不一致 |
| I12 | **Web 防护** | Host 非回环 / mutation 带非本机 Origin → 403（LocalControlPlaneGuard） |
| I13 | **数据源沙箱** | Web 新增 file:// 仅限 BINGGO_HOME（percent-encoding 解码后校验） |
| I14 | **重试语义** | WBI/明确幂等读请求可按瞬态错误重试；业务码错误不重试；非幂等写遇到结果未知不得自动重发 |
| I15 | **探测三态** | True/False/Unknown 明确区分；Unknown 不触发关注/收藏/转发/评论写副作用 |
| I16 | **调度代际** | stop 返回后旧 generation 不再发布事件或投递任务；同一时刻最多一代活跃 |
| I17 | **导入原子性** | 核心表与 DS/WATCH 快照同一事务，或显式 staged/partial_commit/resume，不得无标记半导入 |
| I18 | **mutation 门禁** | Job 运行期间不得变更该 Job 绑定的执行上下文或与其存在资源冲突的数据；当前实现以全量 fail-closed 满足（运行中所有 mutation 返回 JOB_BUSY），安全例外显式 allowlist；若按资源冲突收窄，必须保持 fail-closed 语义并补逐路由测试 |
| I23 | **Job 身份冻结** | `account_uid` 只能由服务端在创建时绑定，禁止从 `params` 注入；worker 在 `run_action` 前核验当前有效 UID，匹配才执行，NULL 仅兼容 login/历史任务 |
| I19 | **DS-10 网络与日志** | 目标地址和每次重定向经过网络策略；原始 URL 不进入异常、Job、SSE、诊断和前端 |
| I20 | **任务可寻址** | 等待、取消、终态查询按 job_id，不按 action 猜测目标 |
| I21 | **维护脚本安全** | 破坏性脚本默认 dry-run，`--apply` 才写入，输出目标/归属/数量 |
| I22 | **安装器进程安全** | 只操作本安装 PID/路径，不按镜像名全局强杀 |

## 5. 发布验收

| # | 检查项 |
|---|---|
| R1 | `src/app_paths.__version__` 已 bump（SSOT）且 git tag 对应 |
| R2 | merge 到发布分支前 CI 与受影响测试必须通过（commit 不设全量测试硬门槛）；推送 `selinyi123/bil-1` main 或发布 Release 必须有用户明确发布授权 |
| R3 | build.ps1 产出 Setup + Portable，版本号与 __version__ 一致 |
| R4 | 覆盖安装后 8181 可用、功能冒烟（F1/F6 至少） |
| R5 | 仓库内文档同步：AGENTS.md、SPEC.md、ACCEPTANCE.md、docs/13、docs/14 审计底稿；Obsidian 01–12 为个人知识库可选镜像，不作为发布阻断项 |
| R6 | 发布 SSOT 一致 | `src/app_paths.__version__`、更新 API、前端 Release、installer 和构建产物版本/仓库一致 |
| R7 | 证据包 | 保存测试/构建命令、版本、产物路径、未验证项和风险接受记录；不包含任何 secret |

## 6. 审计追踪

审计 ID → 验收项映射、修复顺序与关闭记录见 `docs/14-全量逐函数与漏洞审计-2026-08-12.md`（§7 修复顺序、§8 回归矩阵、§8.1 映射）。关闭审计项时在底稿中标记“已修复”并附代码位置与测试证据，不删除历史结论。

## 7. 新增行为的验收模板

新增功能或修复缺陷时，PR/变更说明至少填写：

1. 输入与身份：调用入口、uid/job_id、配置快照；
2. 外部副作用：请求方法、是否幂等、结果未知如何处理；
3. 持久化：写入表、事务边界、失败回滚/恢复；
4. 安全边界：secret、URL、Host/Origin、路径、进程归属；
5. 测试：按风险模型覆盖适用维度（success / validation failure / external failure / unknown outcome / retry / cancellation / concurrency / boundary）；高风险外部副作用至少覆盖 failure + unknown outcome；无对应语义的维度（如纯展示改动）不强制；
6. 文档：更新 SPEC/ACCEPTANCE 相应章节（审计类状态写入 docs/14）；
7. 证据：实际命令与结果，未执行项明确标注。
