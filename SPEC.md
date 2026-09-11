# Binggo 系统规格（SPEC）

> 交接文档（2026-08）。面向接手开发：描述系统边界、数据模型、关键机制、当前状态与已知 gap。
> 审计状态（缺陷、证据、修复顺序、关闭条件）唯一来源：`docs/14-全量逐函数与漏洞审计-2026-08-12.md`；Obsidian 01–12 为个人知识库可选镜像。

> 最近审计：2026-08-12（底稿 docs/14）。本文中的“必须/不得”是目标不变量；“当前状态”是代码快照事实，修复前不得当作已通过。

## 1. 系统概述

Binggo 是本机（local-first）B 站抽奖助手：数据源发现抽奖活动 → SQLite 活动库 →
Web 控制台（仅 127.0.0.1）浏览与参与 → 定时自动参与 → 中奖提醒 → 过期清理。
数据（Cookie、活动库、参与记录）只在本机，不上云。

- 技术栈：Python 3.12 · FastAPI · SQLModel/SQLite（WAL）· Vite + TS（无框架）· PyInstaller + Inno Setup
- 入口：`binggo_launcher.py`（launcher 守护 serve 子进程，`--serve` 模式跑 `src/dashboard_server`）
- 端口：源码 8787，打包版 8181（`dashboard_server` 按 `is_frozen` 区分）
- 版本 SSOT：`src/app_paths.__version__`（当前值以代码为准，本文不写死）；发布仓库 `selinyi123/bil-1`

## 2. 分层与模块

| 层 | 模块 | 职责 |
|---|---|---|
| 领域 `src/` | `bilibili_client.py` | B 站 API：httpx、WBI 签名（`_ApiError` 业务码）、限流、重试 |
| | `bilibili_auth.py` | `resolve_effective_uid()` 身份统一、CSRF/uid 解析 |
| | `account_pool.py` | 多账号池（{uid}.txt + active + {uid}.json proxy）、原子切换回滚 |
| | `sources/` | DS-1~10 数据源（fingerprint 增量、`commit_source_checkpoint`） |
| | `source_settings.py` | DS-8/9/10 Web 受控配置（file:// 沙箱、URL 脱敏） |
| | `pipeline/` | 发现流水线：去重→分类→enrich（每 worker 独立 client）→落库 |
| | `participation*.py` | 参与编排、单事务持久化、文案、前置校验 |
| | `lottery_actions.py` | 动作执行 + `ActionResult(extra)`（created_dynamic_id） |
| | `clear_follows.py` | 清理（exact ownership、默认 dry_run、分区取关） |
| | `draw_check.py` / `notify.py` | 中奖深检（送达确认）、15 渠道通知（业务码校验） |
| | `db/` | SQLite schema v4、activity/participation store、import、snapshots |
| API `web/` | `app.py` | FastAPI 路由 + 中间件链（AssetCache→ApiContract→LocalControlPlaneGuard） |
| | `actions.py` | run_action 统一执行器（refresh_all/participate/三连/check_prize/clear_follows…） |
| | `product_routes.py` | 新架构路由（source-settings、settings/proxy） |
| | `job_runner.py` / `auto_scheduler.py` | 任务状态机 + 定时调度 |
| | `local_guard.py` | Host/Origin 校验（DNS rebinding + 跨站 mutation 防护） |
| 前端 `web/frontend/` | Vite + TS | 无框架模块化：settings/sources/jobs/account/activities/shell |
| 扩展 | `mcp/` | MCP stdio（仅 HTTP 调控制台，不改业务） |
| | `scripts/` | 约 30 个运维/迁移/调试脚本 |
| | `packaging/` | Windows/macOS 打包（build.ps1、binggo.spec、installer.iss） |

## 3. 数据模型（SQLite，schema v4）

- `activities`：活动库（payload_json 全量 + 升格列）；`participations(uid,dynamic_id)`：用户状态
- `participation_actions`：动作台账（actions_json 含 `extra.created_dynamic_id`，清理 ownership 依据）
- `jobs`：任务（state/error_kind/message/result_json…）；`account_uid` 为服务端绑定的实际账号，历史任务和 login 可为 NULL
- `account_profile_cache(uid 主键)`：账号资料缓存（v3 迁移，不再串号）
- `source_checkpoints(source_id)`：数据源 checkpoint（cv_id 存 fingerprint）
- `watch_users` / `message_watch` / `draw_reminder_snapshots` / `watch_sync_snapshots` 等
- `SchemaMeta(id=1, version=4)`：版本门禁（未来版本 hard fail）

迁移约定：`init_db` 顺序 = 读 schema_meta → 版本高于代码 **在任何写操作前 hard fail**（绝不降级回写）→ 顺序迁移 → `create_all`。schema_meta 行缺失且存在业务表 → 拒绝启动（fail-closed）。

## 4. 关键机制

### 4.1 身份与多账号
- `resolve_effective_uid()`：BILI_COOKIE env > 账号池活跃 > cookies.txt——UI 显示与实际请求身份必须一致。
- BILI_COOKIE env 生效时：`set_active` 拒绝切换、扫码登录仅登记、legacy 收养跳过、`has_login_cookie` 识别 env、logout 返回明确错误。
- `set_active`/`register_login_cookie`：先写 cookies.txt 再写 active，失败回滚（原子性加固）。
- 账号级 Proxy：`accounts/{uid}.json`；`get_proxy_url(uid)` 三层优先 env > account > global；proxy.json mtime 热更新。
- **共享 `ActivityRow` 的账号态字段一律需要溯源**：`activity_status` 由多条路径写入、
  `platform_participated`（`notice.participated`）与 `reserve_reserved`
  （`fetch_reserve_button_status`）来自带登录态的接口，三者都是**账号态事实**却存在共享行。
  平台事实随写入记录 `platform_observed_uid`，读侧仅在观测账号 == 当前账号时才采信；
  遗留数据无溯源一律不信任（fail-closed，代价是重复一次幂等参与动作）。
- **共享 `ActivityRow.activity_status` 不是账号状态权威**：它由 `apply_initial_status` /
  `status_refresh` / `participation` 多条路径写入，跨账号共用同一行。账号态的唯一权威是
  `ParticipationRow(uid, dynamic_id)`。读侧（`web/activity_service._resolve_activity_status`）
  对可参与活动一律走 `src.activity_status.resolve_activity_status()`，按
  「已结束 > per-UID participation > 平台事实 > 默认」判定；只有不可参与类型才回落共享字段。
  新增读路径不得再以共享 `activity_status` 短路，否则会跨账号污染。

### 4.2 参与链路
- `run_action("participate", {dynamic_id})`：**无预演模式**，调用即真实执行并写入参与记录。
  参与是幂等探测过的低风险动作，预演只能复述固定的五个步骤，提供不了决策信息，
  却要求 `dry_run` 在 HTTP → action → domain 四层正确透传——该契约历史上被中层写死过一次，
  行为与声明完全相反。预演仅保留给 `clear_follows` 这类真·破坏性操作。
- 动作顺序：like → follow → favorite → repost → comment（各动作独立，失败继续，actions 精确记录）；follow 失败后不建/移关注分区。
- 结果持久化：`record_participation_outcome_unlocked` **单事务**写 participation_actions + participations + activities。
- 三连：`fail_fast_event`（内部失败）与 `cancel_event`（用户取消）分离；失败终态 `error`（`error_kind=business_partial`），`partial_failure` 结果携带已完成活动摘要 + 已开始动作（partial:true）。
- `ActionResult.extra`：repost 成功记录 `created_dynamic_id`（清理 exact ownership 的依据）。

### 4.3 数据源与发现
- DS-1~7：UP 合集/话题专栏（video/cv/opus_post）；DS-8 手动清单；DS-9 话题；DS-10 外部 API/JSON（URL 或 file://）。
- 增量：内容 fingerprint（sha256/ETag/Last-Modified）存 `SourceCheckpointRow.cv_id`；内容未变 → `updated=False` 不触发流水线；空批次/清空配置推进指纹（旧 snapshot 不再残留）；DS-10 全部源失败显式抛错。
- 安全：DS-10 URL hash 为 key（凭据不落库）；Web 新增 file:// 仅限 BINGGO_HOME（先 unquote 防 %2e%2e）；`mask_external_source` 只回显 origin。
- 流水线：分类（LLM 兜底）→ enrich（每 worker 独立 client，池式取还）→ 落库；只处理新链接。

### 4.4 任务模型
- **写者锁（`src/writer_lock.py`）**：`data/binggo.writer.lock`，跨平台非阻塞文件锁，
  保证**同一时刻本机只有一个任务级写者**（JobRunner 任务 + 有副作用的 CLI）。
  **不覆盖** Web GET 路径的维护性写入与配置类 mutation 端点——持锁不等于
  "DB 此刻不会被改"，勿据此写 read-modify-write。`JobRunner.try_start` 与四个有副作用的 CLI
  （participate / maintain_local_activities / purge_all_dead_links / rollback_ds_containers）
  共用同一把锁。`JobRunner` 的单槽只是 Web 进程内互斥，管不到 CLI；跨进程正确性由本锁承担。
  无 `--force`，无阻塞等待；CLI 拿不到锁即退出码 2。与 `binggo_launcher` 的单实例锁
  是两件事（那把答"只跑一个 launcher"，这把答"只有一个写者"）。
- `JobRunner`：先取写者锁再占内存槽；取不到锁等同"已有任务在跑"（返回 None → API 报 JOB_BUSY）。
  单槽互斥、状态机（running/success/error/cancelled/interrupted）、`error_kind` 分类
  （internal/business/business_partial/cancelled/network）、SSE 事件、启动恢复。
  锁在 worker 线程 finally 中释放，异常路径同样释放。
  `error_kind` 增加 `identity` 分类。
- **Job 身份策略（`web/job_runner.JOB_IDENTITY_POLICY`）**：每个 action 必须显式登记，
  未登记者默认按 `bound` 处理并要求 `account_uid`——新增 action 忘了登记会被拒绝启动，
  而不是静默放行。三种策略含义**不可混为一谈**：
  - `unbound`（仅 `login`）：不需要账号身份，它的目的就是取得身份。
  - `bound`（refresh_* / check_prize / clear_follows）：创建时由服务端
    `resolve_effective_uid()` 绑定 `account_uid`（不接受客户端 params 传入），
    worker 起步再核对一次，不一致则 fail-closed 为 `error_kind=identity`。
    **这是身份准入检查与审计标记，不是凭据冻结**——任务执行期间各自建客户端，
    其安全性部分依赖「任务运行期间禁止 Web 切号」（`_reject_when_job_running`）。
    若将来允许运行中切号，这些 action 要么升级为 `context`，要么在关键身份操作处重新验证。
  - `BilibiliClient(account_context=..., proxy=...)` **同时传两者会抛 ValueError**：
    context 的代理是执行身份的一部分，而显式 `proxy=` 表达的是调用方自己的意图；
    静默采纳任一方都会让另一方失效，属于调用点的错误，不由构造函数替调用方决定。
  - `context`（`participate` / `participate_triple`）：在 `bound` 基础上再
    `capture_current_account_context(expected_uid=...)` 捕获不可变 Cookie/CSRF/UID/Proxy
    快照，整个任务用同一份凭据。捕获时会**重新**从 Cookie 解析 UID 并要求与绑定 UID 相等，
    因此不是"检查完就盲跑"的 TOCTOU。
- **平台事实与溯源是不可分割的元组**（`status_refresh.PLATFORM_FACT_FIELDS`）：
  `platform_participated` / `reserve_reserved` / `platform_observed_uid` 必须同进同出。
  更新 fact 而保留旧 provenance 会制造「B 的事实 + A 的 observed_uid」，
  让读侧误认为是当前账号自己观测到的结果，绕过 4.1 的账号隔离。
  账号绑定 preflight 的 `observed_uid` 取绑定 UID，并断言 `client.login_uid` 与之一致。
- `AutoScheduler`：时间槽触发（refresh_all 批次 + participate_triple）；`_is_hard_failure` 按 error_kind 判定（字符串兜底）；触发前校验 `validate_job_prerequisites`（未登录/LLM 未就绪 soft skip）。
- **撞车不再停机**：`CollisionError` 由 fatal 改为**跳过本时间槽**（标记该 slot key 已处理，
  下个槽照常）。一次撞车让调度器死到人工重启属于"一次失败长期降级"；正确性归锁，韧性归调度器。
  调度器**从不** `cancel` 对方正在运行的任务。
- refresh_all 三态：全失败 → `ok=False`；无更新+部分失败 → 消息明示 + `sources_failed`；**已知 gap**：有更新+部分失败时 result 仍缺 `sources_failed`（待完善）。

### 4.5 安全边界
- `LocalControlPlaneGuard`：/api/* Host 校验（仅 127.0.0.1/localhost/[::1]，DNS rebinding 防护）+ mutation 方法 Origin 校验（非本机 403）。
- 通知凭据：`SENSITIVE_FIELDS` 全渠道脱敏（含 bot_token/pass/push）；PUT 响应再次 sanitize；`notify.json` 走 `write_text_secret`。
- `clear_follows`：默认 dry_run；只删 `created_dynamic_id` 精确匹配（旧记录按源 id 兼容）的转发；白名单同时保护删除与取关；`partition_name` 未显式时沿用参与配置自定义分区。
- 中奖深检：至少一个渠道确认送达后才 mark DM read（`delivered`/`acknowledged`）；`judge_keywords([])` 显式禁用。
- 通知渠道：`_http_ok` 必须先要求 HTTP 2xx，再按 provider 业务码校验（fail-closed）；飞书官方签名（HMAC key=`timestamp\nsecret`，msg 空）。3xx 不得进入 `sent`。


### 4.6 LLM
- 仅转发抽奖解析使用（forward_parser：`_strict_bool` 严格布尔、`_extract_json_object` raw_decode）；`test_llm_connection` 校验 `choices[0].message.content` 结构。

### 4.7 多账号串行轮转
- **只串行，不并行**：并行要拆掉「全机同时只有一个写者」（§8 #7），那是改地基不是加功能。
  轮转发生在时间槽之间，`JobRunner` 单槽与写者锁语义完全不变。
- **无记忆**：轮到谁由 `rotation_uid_for_slot()` 从槽 key 派生（`时*12 + 分//5` 对账号数取模，
  账号按 uid 排序），**不存游标**。因此不存在"上次轮到谁""上次谁失败了"这类状态——
  账号冷却/灰度/健康度是 `AGENTS.md` 机制判据明确拒绝的账号级 FSM。
  代价：增删账号会让映射整体平移。轮转不承诺公平配额，只承诺每个号都会轮到。
- **不切 active**：`capture_account_context_for_uid()` 直接读 `accounts/{uid}.txt`，
  不经过 `cookies.txt`，UI 顶部身份不受后台任务影响，也不反复重写配置文件。
  身份正确性由该函数自身保证（存的 cookie 解析出的 uid 必须等于请求 uid，否则 fail-closed）。
- **轮转任务跳过"绑定 UID == 生效身份"校验**：那道校验守的是「任务创建后活跃账号被切走」，
  与轮转要表达的意图相反。`JobRunner.try_start(capture_uid=...)` 是唯一入口，
  UI 手动发起的任务不传它，原有 fail-closed 一字未动。
- **开关不持久化**：`POST /api/auto/start {"rotate_accounts": true}`，仅本次运行有效，默认关闭。
  调度器自身重启即停，开关比它活得久会造成"我以为没开轮转，一按启动就用多个号操作"。
- **服务端可拒绝**：账号池不足 2 个、或 `BILI_COOKIE` 覆盖身份（env 表达的是"所有请求都用
  这个身份"，与逐账号轮转互斥）时不启用，回执 `rotate_accounts=false` 并记日志。
- **范围**：`participate_triple`（非整点小时的 `:05`~`:55`）与 `check_prize`（整点小时的 `:30`）。
  `refresh_*` 写的是**共享**活动表，换个账号跑得到同一批结果，纯属放大对 B 站的请求量；
  `clear_follows` 是破坏性动作，不进无人值守轮转。
- **轮转序号只能相加，不能相乘**：任何乘数 `k` 都会在 `k % 账号数 == 0` 的池规模上
  让那一项整个消失。踩过两次——`时*12` 让 2/3/4/6/12 个账号的小时项失效（每个 uid 的
  动作时刻永久固定在同一组「分」上，是可观测的关联签名）；改用「本日第几个整点」后
  又写成 `yday*8`，8 对 2/4/8 取模为 0，最常见的池规模下 `00:30` 永远归 uid 最小的号。
  现在两个函数都是纯相加（`gcd(1, n) = 1` 对每种池规模成立）。守卫测试按池规模参数化，
  否则用 3 个账号测恰好落在能平移的那档。
- **深检刻度可补跑**：`_run_refresh_batch` 同步阻塞整个调度线程（三次 `_wait_until_terminal`，
  上限六小时），用 `minute == 30` 精确匹配的话，批次跑到 `:47` 才返回时那一刻度根本不被
  求值，静默消失。判据改为「已过 `:30` 且本小时未跑过」，槽 key 固定用 `:30` 保证补跑时
  选到的账号与准点一致。
- **三连刻度不补跑，这是结论不是遗留**：它同样是精确分钟匹配，长批次同样会吃掉跨过的刻度。
  但两者的密度差三个数量级——三连每天 176 个刻度（16 个非刷新小时 × 11 个五分钟位），
  深检每天 8 个、间隔 3 小时。批次结束后最多 5 分钟就有下一个三连刻度，而候选是
  「尚未参加的活动」，它们不会因为刻度被跳过而消失，下一刻度照样选得到。**没有东西被永久漏掉，
  只是那段时间吞吐降低**。深检不同：错过 `:30` 要等 3 小时，中奖通知与私信已读同步延迟。
  反过来说，给三连加补跑会在长批次刚结束时立刻打一次、5 分钟后再打一次，
  制造的正是我们在 §4.7 其余条目里小心避免的突发请求特征。
- **`check_prize` 已升级为 `context`**：它会 `mark_dm_read()` 标记私信已读，是代表用户的写入；
  不冻结凭据的话，轮转时它会按"当前活跃 cookie"去读并标记**别的号**的私信。
  **对手动执行也有行为变化**：上下文捕获要求 cookie 同时解析出 uid 与 csrf，
  而 `bound` 不做这个检查。只有 SESSDATA、缺 `bili_jct` 的 `cookies.txt` 现在会在捕获阶段
  直接失败——标记私信已读本就需要 csrf，早失败优于跑到一半失败，但这是轮转之外的路径。
- **定时深检一律推送**：`_click_and_wait` 只给 `participate_triple` 传参数，`check_prize`
  拿到空 dict，于是 `params.get("push", True)` 恒为 True。设置页那个推送勾选框只作用于
  手动执行，界面上已注明。
- **中奖通知带账号标识**：`_account_label()` 从账号资料缓存取昵称，取不到则只写 UID。
  轮转下不写清是哪个号，收到"命中 N 条"也不知道去哪个号领奖。
- **候选按执行账号的台账筛**：`pick_triple_participate_targets(viewer_uid=...)`，
  轮转任务传绑定账号的 uid，UI 手动三连不传（落回活跃账号）。
  **这句话此前写在规格里但代码没做**：写入端是 per-uid 的
  （`participate_activity(account_uid=account_context.uid)` 落 `ParticipationRow(uid=B)`），
  读取端却一路 `participation_uid()` → `get_active_uid()`。隔离只封了写路径的一半，
  后果双向：A 参加过的活动 B 永远轮不到，B 自己参加过的下一槽仍显示「未参加」而被**重复参与**。
  与不变量 #3 是同一形状的缺陷——都把「执行身份」误读成「当前活跃身份」。
- **已知取舍**：各账号仍会参与**同一批**活动（活动库共享，每个号各自取自己未参加的前几条）。
  产品决策为允许；多号参与同一抽奖通常违反活动规则，中奖可能被取消，且是较强的账号关联信号。
  未配独立代理时会共用出口 IP——启动时**只警告不阻止**。

## 5. 当前状态

- 测试与构建验证记录（含历史数字）见 docs/14 §6；验收不设固定测试数量门槛（ACCEPTANCE T1）。
- 历轮审查修复、LAS 迁移接线和前端产品化以当前工作区代码为准；远端推送需以本次发布证据确认。
- 安装器覆盖安装与 8181 启动属于发布验收项，当前文档不以历史文字代替实际证据。
- 审计底稿：`docs/14-全量逐函数与漏洞审计-2026-08-12.md`。

## 6. 已知 gap / roadmap（详见 docs/13-LAS功能迁移审计.md）

- **单条技术失败的链接会被永久遗漏（已知取舍，不是 bug，勿修）**：
  `run_new_links_pipeline` 单条 classify/enrich 技术失败记入 `skip_reasons` 后继续，整体正常返回；
  上层随后照常 `commit_source_checkpoint`。若上游容器此后不再变化，该链接不会再进入增量发现。
  **这是有意选择**——按 `AGENTS.md` 的机制判据，失败重试表属于制度层，已否决；
  「失败就不推进 checkpoint」被判定为不值得的额外处理。跳过失败、继续下一条即为最终语义。
- ~~**GET 路径存在维护性写入**~~（**已关闭**）：三处读路径写入已分别处理，
  见 §8 不变量 #14，守卫测试 `tests/test_get_no_write.py`（4 例，均先在旧代码上验红）。
  - 活动过期 UPDATE → 读时派生（`src/activity_store.derive_payload_for_read`），
    `refresh_expired_activity_statuses()` 删除；
  - `seed_from_candidates_if_empty()` / `ensure_legacy_account()` → 挪入
    `src/app_paths._bootstrap_user_data()`，与既有的种子灌入同处执行；
    `web/product_routes._require_local_account()` 里的第四处收养一并移除
    （它被 `GET /api/settings/proxy` 走到，仅在已登录时可达，原 gap 未记录）。
  - 验证：全量 `python -m pytest -q` 通过。**测试数量不写进文档**——它每次改动都变，
    写下来只会变成又一处需要维护的陈述（docs/13 已立此规则，此处此前违反过）。
- **活动列表读取仍是全表加载**：`_filtered_activity_rows` 先把整表读进 Python 再过滤、
  排序、切页（`ACTIVITY_PAGE_SIZE = 20`），复杂度随活动量线性增长。
  实测（本机，隔离库，一半活动已过期）：

  | 活动条数 | `/api/activities` | `/api/summary` |
  |---|---|---|
  | 100 | 10.8 ms | 18.5 ms |
  | 1000 | 43.8 ms | 43.3 ms |
  | 2000 | 76.3 ms | 71.7 ms |
  | 5000 | 187.2 ms | 171.3 ms |

  拆解（N=2000）：SQL 取行 17ms、`payload_json` 全量 decode 约 30ms、其余约 29ms。
  **大头是为返回 20 条而解码全部行**，而过滤/排序/计数所需字段全是升格列，
  无需解码 payload。两条可选路径：只解码当页（省约一半），或过滤/分页下推 SQL
  （`ix_activities_lottery_time` 已存在）。
  **当前决定：不做**——本机单人控制台，2000 条时 76ms 无感知。库超过约 2000 条
  （控制台"共 N 条"）再重评。

- **多账号编排**（**串行轮转已落地**，其余仍是产品决策）：`participate_triple` 与 `check_prize`
  支持按时间槽逐账号轮转，见 §4.7；并行隔离、账号健康度**已明确否决**（拆单写者不变量 /
  违反机制判据），`clear_follows` 的 Context 化与 `refresh_*` 的账号维度仍未做。
- **身份边界只覆盖 5 / 28 个客户端构造点，调用点仍看不出区别**：传 `account_context` 的
  5 处是 `actions.py` 的三个 `context` action 加 `account_service.get_account_profile(uid)`
  的轮转前置校验；其余 23 处（10 个数据源、`refresh_all_pipeline` 的 shared client 与 worker
  池、`watch_*`、`fetch_activity_info`、`clear_follows`、全部 `scripts/`）按环境身份解析。
  **这与 `JOB_IDENTITY_POLICY` 一致，不是 bug**——`refresh_*` 与 `clear_follows` 本就是 `bound`。
  真正的问题是 `BilibiliClient()` 与 `BilibiliClient(account_context=ctx)` 在语法上无从区分意图，
  `check_prize` 因此漏过一次。`test_context_actions_are_plumbed.py` 已强制每个 `context`
  action 登记接线测试，堵住了「新增 action 忘记透传」这一条路径；**尚未做**的是让
  `account_context` 成为必填参数（显式传 `None` 表示环境身份），那才是消灭二义性本身。
- **导入 `web.app` 有真实的 import 期副作用**（外部复审指出，**此前本节误记为"无"**）：
  模块顶层执行 `ensure_user_dirs()`（创建目录、分发种子配置）、`setup_logging(console=False)`
  与 `runner.recover_on_startup()`（把残留 running 任务改写为 interrupted，**写库**）。
  这是 FastAPI 单进程应用的常见形态、也是 `_bootstrap_user_data` 得以把写入挪出 GET 路径的落点，
  因此**不判定为缺陷**；但「import 即建目录、即写 jobs 表」必须写下来——
  任何以 `import web.app` 为前提的脚本、测试或工具都在这个前提之下运行。
  （前一版结论"全仓无 import 期 I/O"是错的：当时的检索只匹配 `name = call()` 形式的赋值，
  漏掉了裸函数调用。检索方法本身是缺陷来源，记在这里。）
- **事件总线的 protected 事件并非绝不丢**（外部复审指出，**此前本节误记为"绝不丢终态"**）：
  队列被 256 条 protected 事件填满时，`_make_room_locked` 回填上限是
  `queue_maxsize - reserve = 255`，`keep[:255]` 会截掉最新的那条 protected；
  incoming 若也是 protected 则走 `put_nowait` 失败分支并记 warning。
  正确表述是「背压优先丢进度噪声，protected 事件只在队列被 protected 自身填满时才丢，且留日志」。
  一个 SSE 消费者要卡到积压 256 条终态事件才会触发，**当前不修**，但不得再写成无条件保证。
- **`classify` 串行是真实的吞吐损失，并发确实有用**（外部复审纠正了前一版的论断）：
  令牌桶的 `acquire()` 取到令牌即返回，网络等待发生在其之后，因此串行链路的实际速率是
  `min(3 rps, 1/RTT)`——RTT 超过约 333 ms 时限速器根本没打满，令牌白白流走。
  `enrich` 阶段的 worker client 池正是为此存在（每个 `BilibiliClient` 有自己的 `_http_lock`，
  共享单 client 会串行化 HTTP）。所以此前「二者必有一处判断是错的」的答案是：
  **enrich 的池子是对的，classify 的单 client 串行是那一处错**。
  成本模型仍是「请求数 × 限速」——`classify_new_link` 每条链接 3~5 个请求，N 条约 `4N/3` 秒
  是**下界**；降低每条链接的请求数依然是更大的杠杆，但有界并发是真实且未采摘的收益。
- **`get_engine()` 每次调用都做一次文件系统 realpath**：`db_path().resolve()` 在全局锁内执行，
  实测 31.5 µs/次，其中 27.7 µs 是 resolve；空 `session_scope()` 共 84.7 µs，三分之一花在解析
  一条运行期不会变的路径上。55 个调用点，是全应用最热的路径。缓存解析结果即可，
  重建逻辑（DATA_DIR 变化时换库）保留。
- **覆盖率的缺口集中在副作用不可回滚的模块**：全量约 70%。
  但 `lottery_actions` 37.8%（400 语句）、`notify` 37.7%（300）、`bilibili_client` 42.4%（467）、
  `participation` 53.9%（267）——这四个模块合计约 1400 语句，平均覆盖不到一半，
  而它们正是真实账号上真实动作的执行层、送达层、传输层与台账层。
  纯逻辑模块（codec、status、time、parser）反而覆盖良好。**方向反了。**
- **不存在「库 + JSON 双轨持久化」**（两轮外部复审各误判过一次，记在这里免得第三次）：
  `data/output/*_latest.json` 这些路径看着像第二个存储，实际**没有任何代码写它们**——
  `sources/common.save_result()` 只调 `save_ds_check_dict()` 落库，`path` 仅作返回值。
  读侧 `load_previous_output(path)` 也不读文件，它拿**文件名当键**去查快照表。
  即路径是 DB 行的寻址方式，不是落盘位置。唯一真实的取舍是这个寻址方式本身：
  它曾让 ds8/ds9/ds10 漏登记而静默回退到不存在的文件（已修，映射改为从
  `SOURCE_OUTPUTS` 派生，守卫 `test_snapshot_filename_registry.py`）。
  彻底的修法是让快照按 source_id 寻址、废掉文件名，需改 10 个数据源模块，**未做**。
- **粉丝数线路无记忆**：`get_user_followers` 的 card → relation/stat 两线每次调用都从第一条开始，成功线路不跨调用保留。
- **per-account 行为配置 / 通知身份上下文**：participate_enhance/notify 仍全局；多账号编排落地后需带账号身份。
- ~~**refresh_all 有更新+部分失败时 result 缺 sources_failed**~~（**已关闭**）：三态现在都返回
  该字段，消息也明示失败数。守卫：`test_refresh_all_progress.py` 三例覆盖全失败 /
  无更新+部分失败 / 有更新+部分失败。
- **产品决策项**：AI 评论、only_followed 降级、随机动态（当前 B 站环境价值待验证）。
- ~~**npm audit**~~（**已关闭**）：`npm audit` → 0 vulnerabilities。`nanoid`/`postcss` 走
  `npm audit fix`；其余 5 条（含 1 critical）全部来自 `vitest@2` 内嵌的 `vite@5.4.21` +
  `esbuild@0.21.5`，升 `vitest@5` 后复用顶层 `vite@6.4.3`，整簇消失，配置无需改动。
  同时移除未使用的 `jsdom`（`vitest.config.ts` 用的是 `environment: "node"`，源码零引用）。

## 7. 审计状态

当前已知缺陷（A-01~C-07）的严重度、证据、修复顺序与关闭条件见 `docs/14-全量逐函数与漏洞审计-2026-08-12.md`；本文不复制审计寄存器。关闭审计项时更新底稿并附代码位置与测试证据。

2026-09-11 做过一轮全项目复审（隐藏副作用 / 兼容性 / 性能 / 测试充分性 /
胶水层 / 架构）。**结论与证据写在 docs/14 审计底稿**，不在本文重复；
由它产生的未关闭条目已并入 §6。

## 8. 设计不变量

> **这一节的写法是有意的。** 上一版把不变量写成六条抽象原则，其中
> 「分页收缩不影响最终覆盖」和「运行中 mutation 不得改变上下文」**在写下之后
> 仍然各被违反了一次**（见下表"曾被违反"列）。原因是抽象原则没有落点：
> 读的人无法判断该去哪一行代码检查它，改代码的人也不会在破坏它时收到任何信号。
>
> 因此每条不变量必须同时给出**强制点**（哪段代码承担它）与**守卫测试**
> （破坏它时哪个测试会红）。没有守卫测试的不变量等于没有不变量——
> 新增不变量时请一并补测试，而不是只增加一行描述。
> 本节自身的自洽性由 `tests/test_spec_invariants_are_guarded.py` 守：
> 表中引用了不存在的测试文件、或某行不变量没填守卫测试，都会失败。

### 8.1 跨层不变量

这些不变量的共同特征是：**没有任何单个函数写错**，缺陷只在两个各自正确的
机制组合处出现。它们是本项目历史上缺陷最集中的地方。

| # | 不变量 | 强制点 | 守卫测试 | 曾被违反 |
|---|---|---|---|---|
| 1 | 共享 `ActivityRow` 的账号态字段不是账号状态权威；可参与活动的展示状态一律由 `resolve_activity_status()` 按「已结束 > per-UID participation > 平台事实 > 默认」判定 | `web/activity_service._resolve_activity_status` | `test_activity_service_status_authority.py` | ✅ 读侧曾以 `status_classified` 短路，遮蔽 per-UID 参与记录 |
| 2 | `platform_participated` / `reserve_reserved` / `platform_observed_uid` 是**不可分割的元组**，必须同进同出 | `src/status_refresh.PLATFORM_FACT_FIELDS` | `test_platform_fact_provenance.py` | ✅ 账号绑定路径恢复 fact 却保留新 provenance，制造「B 的事实 + A 的标签」 |
| 3 | 平台事实的 `observed_uid` 必须是**实际发出请求的身份**，不是"当前 active 账号" | `participate_preflight`（断言 `client.login_uid == account_uid`） | `test_platform_fact_provenance.py` | ✅ 曾用 `participation_uid()`，与绑定账号可能不一致 |
| 4 | Job 启动时绑定的执行身份在运行中不得改变；`context` 策略的 Cookie/CSRF/UID/Proxy 是冻结快照 | `account_context.capture_current_account_context`、`BilibiliClient.__init__` | `test_account_context.py` | ✅ 注释写着"不要重新解析"，三行后的 `if proxy is None` 就在重新解析 |
| 5 | 每个 Job action 必须显式登记身份策略；**未登记者默认拒绝**，不是默认放行 | `web/job_runner.JOB_IDENTITY_POLICY` | `test_job_identity_policy.py` | ✅ 原 `try_start` 允许 `account_uid=None` 并静默跳过身份守卫 |
| 6 | 对外部集合分页遍历时不得边遍历边修改；先读完再执行 | `src/clear_follows.PARTITION_PAGE_SIZE` 附近的两段式实现 | `test_clear_follows_partition.py` | ✅ 120 人分区只取关 70 人，且**预演与真实执行数字不一致** |
| 7 | 写者锁只仲裁**任务级**写者；持锁**不**代表"DB 此刻不会被改"，不得据此写 read-modify-write；也**不**约束平台侧并发——一个 `participate_triple` 任务自己就开 3 个 B 站会话 | `src/writer_lock.py` 模块文档 + §4.4 | `test_writer_lock.py` | — |
| 8 | 字符串布尔值按字面量判定，不得依赖 `bool()`；`None` 表示"未知"不得被压成 `False` | `src/db/activity_codec._as_bool` / `_as_bool_strict` | `test_sqlite_data_layer.py` | ✅ `bool("false")` 为真，且 `skipped`/`status_classified` 两列原本绕过转换 |
| 14 | **GET 端点一律不得写库**，无例外：可推导的状态读时派生，一次性引导放启动 | 派生：`src/activity_store.derive_payload_for_read`；引导：`src/app_paths._bootstrap_user_data` | `test_get_no_write.py` | ✅ 四处：`_load_activities_payload` 在 GET 里 UPDATE 过期活动（不受 #7 仲裁）、`GET /api/watch-users` 灌候选名单、`GET /api/accounts` 与 `GET /api/settings/proxy`（经 `_require_local_account`）收养遗留 cookie |
| 15 | 选目标读的台账必须是**执行身份**的台账；轮转下活跃身份与执行身份不是同一个号 | `web/activity_service._filtered_activity_rows` 的 `viewer_uid` 参数 | `test_triple_targets_viewer_uid.py` | ✅ 候选一路读 `participation_uid()`，轮转账号据 A 的台账选目标，既漏参与又重复参与；与 #3 同形 |
| 16 | MCP 只经 HTTP 消费控制面：不得 import `src.*` / `web.*`，且它调用的每个 `/api` 路径必须是真实路由 | `mcp/binggo_mcp/client.py`（唯一出口） | `test_mcp_api_contract.py` | — |

> #14 编号接在 §8.2 之后，但性质是跨层的（HTTP 读语义 × 锁边界），故列于本表。
> 这条规则**没有例外**——留一个例外，下一个人就会照着例外写新端点。

### 8.2 领域不变量

| # | 不变量 | 强制点 | 守卫测试 |
|---|---|---|---|
| 9 | 每个外部写动作必须能回答：是否执行、哪个 uid、产生什么 ID、是否可重试；结果未知不得伪装成功或失败 | `ActionResult.extra.created_dynamic_id` | `test_clear_follows.py` |
| 10 | Binggo 创建的动态/关注必须有精确归属证据才可被清理 | `clear_follows._owned_repost_dynamic_ids` | `test_clear_follows.py` |
| 11 | 完整成功、降级成功、业务部分失败、取消、内部失败、网络失败、结果未知必须结构化表达，**不得依赖中文 message 判定** | `JobStatus.error_kind` | `test_auto_scheduler.py` |
| 12 | secret 不进 URL 异常、日志、SSE、诊断、前端 storage 或普通响应；Windows 写盘权限失败不得静默 | `log_redact` / `secrets_inventory` / `config_health` | `test_log_redact.py` |
| 13 | 代码版本、更新 API、Release、installer、构建产物与测试指向同一 SSOT | `app_paths.__version__`、`update_check.GITHUB_REPO` | `test_update_check.py` |

### 8.3 机制判据（新增机制前的准入）

> **这个机制是否让「下一个任务的行为取决于上一个任务的失败」？**
> 是 → 制度层，拒绝；否 → 请求级节流，接受。

完整对照表与已按此移除的机制见 `AGENTS.md`。判据管的是**不要新增**制度层；
8.1 管的是**不要拆开**已有的跨层约束。两者解决的不是同一类问题。

## 9. 规范变更规则

- 新增公开函数、Web mutation、外部写请求、持久化字段、数据源协议、MCP 工具或安装器动作时，更新 SPEC 与 ACCEPTANCE 相应章节；审计类状态只写入 docs/14。
- 新增副作用必须增加成功、失败/取消、结果未知或并发边界测试。
- 关闭 gap 必须附代码位置、测试命令与结果，不能只删除 gap 文本。
- 版本、发布仓库、端口、路径和工具版本只保留一个 SSOT，其他文档引用且不写死当前值；Obsidian 01–12 为可选镜像，不作为仓库验收依赖。
