# Binggo 系统规格（SPEC）

> 交接文档（2026-08 · v5.1.0）。面向接手开发：描述系统边界、数据模型、关键机制、
> 当前状态与已知 gap。详细逐函数分析见 Obsidian 知识库（`D:\TOOL\OBSIDIAN\program\知识库\BILI BINGGO`）
> 与仓库 `docs/`。

## 1. 系统概述

Binggo 是本机（local-first）B 站抽奖助手：数据源发现抽奖活动 → SQLite 活动库 →
Web 控制台（仅 127.0.0.1）浏览与参与 → 定时自动参与 → 中奖提醒 → 过期清理。
数据（Cookie、活动库、参与记录）只在本机，不上云。

- 技术栈：Python 3.12 · FastAPI · SQLModel/SQLite（WAL）· Vite + TS（无框架）· PyInstaller + Inno Setup
- 入口：`binggo_launcher.py`（launcher 守护 serve 子进程，`--serve` 模式跑 `src/dashboard_server`）
- 端口：源码 8787，打包版 8181（`dashboard_server` 按 `is_frozen` 区分）
- 版本 SSOT：`src/app_paths.__version__`（当前 5.1.0）；发布仓库 `selinyi123/bil-1`

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
| | `db/` | SQLite schema v3、activity/participation store、import、snapshots |
| API `web/` | `app.py` | FastAPI 路由 + 中间件链（AssetCache→ApiContract→LocalControlPlaneGuard） |
| | `actions.py` | run_action 统一执行器（refresh_all/participate/三连/check_prize/clear_follows…） |
| | `product_routes.py` | 新架构路由（source-settings、settings/proxy） |
| | `job_runner.py` / `auto_scheduler.py` | 任务状态机 + 定时调度 |
| | `local_guard.py` | Host/Origin 校验（DNS rebinding + 跨站 mutation 防护） |
| 前端 `web/frontend/` | Vite + TS | 无框架模块化：settings/sources/jobs/account/activities/shell |
| 扩展 | `mcp/` | MCP stdio（仅 HTTP 调控制台，不改业务） |
| | `scripts/` | 约 30 个运维/迁移/调试脚本 |
| | `packaging/` | Windows/macOS 打包（build.ps1、binggo.spec、installer.iss） |

## 3. 数据模型（SQLite，schema v3）

- `activities`：活动库（payload_json 全量 + 升格列）；`participations(uid,dynamic_id)`：用户状态
- `participation_actions`：动作台账（actions_json 含 `extra.created_dynamic_id`，清理 ownership 依据）
- `jobs`：任务（state/error_kind/message/result_json…）
- `account_profile_cache(uid 主键)`：账号资料缓存（v3 迁移，不再串号）
- `source_checkpoints(source_id)`：数据源 checkpoint（cv_id 存 fingerprint）
- `watch_users` / `message_watch` / `draw_reminder_snapshots` / `watch_sync_snapshots` 等
- `SchemaMeta(id=1, version=3)`：版本门禁（未来版本 hard fail）

迁移约定：`init_db` 顺序 = 读 schema_meta → 版本高于代码 **在任何写操作前 hard fail**（绝不降级回写）→ 顺序迁移 → `create_all`。schema_meta 行缺失且存在业务表 → 拒绝启动（fail-closed）。

## 4. 关键机制

### 4.1 身份与多账号
- `resolve_effective_uid()`：BILI_COOKIE env > 账号池活跃 > cookies.txt——UI 显示与实际请求身份必须一致。
- BILI_COOKIE env 生效时：`set_active` 拒绝切换、扫码登录仅登记、legacy 收养跳过、`has_login_cookie` 识别 env、logout 返回明确错误。
- `set_active`/`register_login_cookie`：先写 cookies.txt 再写 active，失败回滚（原子性加固）。
- 账号级 Proxy：`accounts/{uid}.json`；`get_proxy_url(uid)` 三层优先 env > account > global；proxy.json mtime 热更新。

### 4.2 参与链路
- `run_action("participate", {dynamic_id, dry_run})`：**dry_run 贯穿到底层**——预演零副作用（不写接口、`persist=False`、不改活动库 joined、`mark_enriched_joined` 跳过）。
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
- `JobRunner`：单槽互斥、状态机（running/success/error/cancelled/interrupted）、`error_kind` 分类（internal/business/business_partial/cancelled/network）、SSE 事件、启动恢复。
- `AutoScheduler`：时间槽触发（refresh_all 批次 + participate_triple）；`_is_hard_failure` 按 error_kind 判定（字符串兜底）；触发前校验 `validate_job_prerequisites`（未登录/LLM 未就绪 soft skip）。
- refresh_all 三态：全失败 → `ok=False`；无更新+部分失败 → 消息明示 + `sources_failed`；**已知 gap**：有更新+部分失败时 result 仍缺 `sources_failed`（待完善）。

### 4.5 安全边界
- `LocalControlPlaneGuard`：/api/* Host 校验（仅 127.0.0.1/localhost/[::1]，DNS rebinding 防护）+ mutation 方法 Origin 校验（非本机 403）。
- 通知凭据：`SENSITIVE_FIELDS` 全渠道脱敏（含 bot_token/pass/push）；PUT 响应再次 sanitize；`notify.json` 走 `write_text_secret`。
- `clear_follows`：默认 dry_run；只删 `created_dynamic_id` 精确匹配（旧记录按源 id 兼容）的转发；白名单同时保护删除与取关；`partition_name` 未显式时沿用参与配置自定义分区。
- 中奖深检：至少一个渠道确认送达后才 mark DM read（`delivered`/`acknowledged`）；`judge_keywords([])` 显式禁用。
- 通知渠道：`_http_ok` 业务码校验（fail-closed）；飞书官方签名（HMAC key=`timestamp\nsecret`，msg 空）。

### 4.6 LLM
- 仅转发抽奖解析使用（forward_parser：`_strict_bool` 严格布尔、`_extract_json_object` raw_decode）；`test_llm_connection` 校验 `choices[0].message.content` 结构。

## 5. 当前状态（v5.1.0）

- 测试：**632 passed, 1 skipped**（97 个 pytest 文件 + 前端 test/build + Playwright e2e）
- 已完成三轮审查修复（40+ 项）+ LAS 迁移接线 + 前端产品化 + 把关修复；均已推送 `selinyi123/bil-1` main
- 已打包安装：`D:\TOOL\BILIBILI LOTTERY\BINGGO\Binggo\Binggo\`（Setup 覆盖安装，端口 8181）
- 知识库已同步：`D:\TOOL\OBSIDIAN\program\知识库\BILI BINGGO`（12 文档追加 2026-08 更新小节）

## 6. 已知 gap / roadmap（详见 docs/13-LAS功能迁移审计.md）

- **多账号编排**（产品决策）：当前是账号池管理，非 LAS 逐账号自动轮转；若做建议 `AccountContext` + Job 绑定 account_uid。
- **Line client-level registry**：当前每次调用新建 Line，valid_line 不跨调用保留。
- **per-account 行为配置 / 通知身份上下文**：participate_enhance/notify 仍全局；多账号编排落地后需带账号身份。
- **refresh_all 有更新+部分失败时 result 缺 sources_failed**（机器化 degraded 未完整）。
- **产品决策项**：AI 评论、only_followed 降级、随机动态（当前 B 站环境价值待验证）。
- **npm audit**：前端 dev 依赖 7 个漏洞告警（打包产物不受影响），建议后续处理。
