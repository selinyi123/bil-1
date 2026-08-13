# AGENTS.md

Binggo —— 本机（local-first）B 站抽奖助手：自动发现抽奖活动、Web 控制台浏览、定时自动参与。Python 3.12 + FastAPI + SQLite + Vite/TS 前端。

## 目标（Product Goal）

- 单机闭环：数据源发现 → 活动库 → 参与 → 中奖提醒 → 清理，全程本机 SQLite，不上云。
- 安全优先：只删 Binggo 自己创建的东西、凭据绝不出本机、local-first 不产生意外副作用。
- 长期稳定：web 服务形态 + 定时调度，对抗 B 站风控（限流/WBI/幂等）。

## 机制判据（新增机制前必须过这一关）

> **这个机制是否让「下一个任务的行为取决于上一个任务的失败」？**
> 是 → 制度层，拒绝；否 → 请求级节流，接受。

「对抗风控」只授权**无记忆的请求级节流**，不授权账号状态机。失败处理的既定做法是
**跳过失败、继续下一条、不做多余处理**（`run_new_links_pipeline` / `tests/test_pipeline_resilience.py`）。

| 允许 | 拒绝 |
|---|---|
| 令牌桶限流（`bilibili_rate_limit`，默认 3 rps） | 账号冷却 / 灰度 / 准备状态等账号级 FSM |
| 动作间随机间隔（`participate_enhance.action_interval_sec`） | 失败重试队列 / 待重试表 |
| 单请求内的业务码退避（-352/-509/-799） | 闩锁式全局降级（需人工或定时 reset 才恢复） |
| 跨进程写者锁（无记忆，用完即释放） | 撞车即停机等「一次失败长期降级」的响应 |

违反此判据的机制已被移除：详情 API 双份熔断器（2026-08）、`AutoScheduler` 的
`CollisionError → fatal`。新增前请先在此表中找到自己的位置。

## 仓库结构

```
binggo_launcher.py       入口：launcher 守护 serve 子进程（--serve 跑 dashboard_server）
src/                    领域层（不依赖 web）
  bilibili_*.py         B 站客户端：WBI 签名、限流、身份 resolve_effective_uid
  participation*.py     参与链路：五连/预约、单事务持久化
  lottery_actions.py    动作执行（like/follow/favorite/repost/comment）、ActionResult(extra)
  sources/              DS-1~10 数据源（fingerprint 增量、checkpoint）
  source_settings.py    DS-8/9/10 Web 受控配置（file:// 仅限 BINGGO_HOME、URL 脱敏）
  db/                   SQLite（schema v4）、activity_store、participation_store
  clear_follows.py      清理（exact ownership：只删 created_dynamic_id 匹配的转发）
  draw_check.py         中奖深检（送达确认后才 mark read）
  notify.py             15 渠道通知（_http_ok 业务码校验、飞书官方签名）
  app_paths.py          路径解析 + 版本 SSOT __version__
web/                    FastAPI：app.py、actions.py、product_routes.py、job_runner.py、
                        auto_scheduler.py、local_guard.py（Host/Origin）、schemas/
web/frontend/           Vite + TS（settings 页、数据源面板、jobs/account/activities）
docs/                   fullstack-roadmap、pipeline-redesign、plans/（方向拍板）、
                        13-LAS功能迁移审计.md（LAS 迁移矩阵与 gap）、
                        14-全量逐函数与漏洞审计-2026-08-12.md（审计底稿）
tests/                  pytest（isolated_home fixture 隔离）
packaging/windows/      build.ps1（vite→PyInstaller→Inno）、binggo.spec、installer.iss
config/                 模板：cookies/llm.env/sources.yaml/manual_dyids/topic_tags/
                        api_sources/notify/participate_enhance（*.example）
```

## Commands（在仓库根 D:\WORK\PROGRAM\DEEPSEEK\BINGGO）

```powershell
# 测试（全量约 60s）
python -m pytest tests/ -q
python -m pytest tests/test_participate_triple.py -q        # 单模块

# 源码运行（控制台 http://127.0.0.1:8787；打包版 8181）
python scripts/run_dashboard.py

# 前端（修改 web/frontend/src 后必须重建，产物 web/static/dist 被 gitignore）
cd web/frontend; npm ci; npm run build

# 打包发布（版本 SSOT：src/app_paths.__version__）
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
# 产物：dist/Binggo/（目录）、Binggo-Portable-win64.zip、Binggo-Setup-win64.exe
# ISCC 路径：D:\WORK\Project Environment\InnoSetup\ISCC.exe（build.ps1 已含搜索）

# 环境：Python 3.12 / Node 20+ / PyInstaller 6 / Inno Setup 6
# Node 不在 PATH 时：$env:PATH = "D:\WORK\Project Environment\NodeJS;...;$env:PATH"
```

## Architecture（承重模块）

1. **身份统一**：`src/bilibili_auth.resolve_effective_uid()` = BILI_COOKIE env > 账号池活跃 > cookies.txt；`account_pool` 多账号 + 账号级 proxy；UI 显示 uid 必须等于实际请求身份。
2. **参与链路**：`participation.py` 编排 → `lottery_actions.execute_full_participation` 执行（ActionResult 记录，repost 带 `extra.created_dynamic_id`）；结果经 `record_participation_outcome_unlocked` **单事务**写三表。
3. **数据源**：DS-1~10 各自 `check_update()` → fingerprint/checkpoint 增量（cv_id 列）→ `refresh_all` 聚合；空批次/清空配置也推进指纹。
4. **任务模型**：`job_runner`（状态机 + error_kind）← `auto_scheduler`（定时）与 `actions.run_action`（UI）；三连用 `fail_fast_event` 与用户取消分离。
5. **安全边界**：`LocalControlPlaneGuard`（Host/Origin 校验）；通知凭据脱敏 + `write_text_secret`；`clear_follows` exact ownership + 默认 dry_run。

## Conventions（必须遵守）

- **清理/删除类操作**：默认 `dry_run=True`；删除前必须归属校验（只删 Binggo 创建的动态，`created_dynamic_id` 精确匹配，旧记录按源 id 兼容）；白名单同时保护删除与取关。
- **凭据**：GET 永不回显真实 secret（`sanitize_config_secrets` 覆盖 bot_token/pass/push）；PUT 恢复后响应**再次 sanitize**；`notify.json` 走 `write_text_secret`。
- **读函数不写库**：`load_payload` 纯读；seed/过期状态更新用显式函数（`seed_activities_if_empty`/`refresh_expired_activity_statuses`）。
- **参与副作用**：参与无预演模式，调用即真实执行（预演只保留给清理这类破坏性操作）；`follow` 失败后不创建/移动关注分区；内部业务失败**绝不 set cancel_event**（终态 `error`/`error_kind=business_partial`）。
- **schema**：未来版本 DB 在任何写操作前 hard fail，绝不自动降级；`init_db` 顺序 = 读版本→hard fail→迁移→create_all。
- **Web mutation**：Job 运行中 fail-closed（`_reject_mutation_while_job_running`）；不得绕过 Host/Origin 校验；按资源冲突收窄的方向见 ACCEPTANCE I18。
- **事务**：参与结果三表（actions/participations/activities）必须同一 session 事务。
- **ORM**：`session_scope` 块内读取字段，块外访问会 DetachedInstanceError（曾致台账静默空集）。
- **测试**：新增/修改行为必须带不变量测试（见 ACCEPTANCE.md）；测试用 `isolated_home` fixture 隔离 BINGGO_HOME 与 DB。

## 规则与索引（2026-08 审计后）

本文件是 agent 的操作速查：安全不变量、协作授权与索引。审计状态（A-01~C-07 缺陷、证据、关闭条件）唯一来源为 `docs/14-全量逐函数与漏洞审计-2026-08-12.md`，本文件不复制审计寄存器。标记为“必须/不得”的条款是开发约束；未闭环审计项不得在发布说明中宣称已通过。

### 不变量索引（完整定义与验收见 ACCEPTANCE.md）

| 不变量 | 验收项 |
|---|---|
| 不确定外部写结果：不重发非幂等 POST；outcome_unknown / 幂等键 | I14 |
| 状态探测三态 True/False/Unknown；Unknown fail-closed | I15 |
| 关注归属：仅本次新建关注入临时分区；预约与五连复用同一归属服务 | I1, F7 |
| 清理分页：先快照或反复读第一页；维护已处理 ID 防死循环 | I1, F7 |
| 调度代际：stop 后旧 generation 不再写状态/投递；同时仅一代 | I16 |
| DS-10 网络边界：异常不含原始 URL；拒绝 loopback/私网/link-local/multicast/unspecified/DNS rebinding | I19 |
| 通知确认：2xx + provider 业务码才记 sent；3xx/非预期 fail-closed | I8 |
| 导入事务：核心表与快照原子提交，或显式 staged/partial_commit/resume | I17 |
| 任务可寻址：按启动时取得的 job_id 收口 | I20 |
| 破坏性脚本：默认 dry-run，显式 --apply | I21 |
| 安装器进程归属：不按镜像名全局强杀；核验 PID/路径 | I22 |
| 发布 SSOT：更新 API/前端 Release/installer/测试统一指向 selinyi123/bil-1 | R6 |
| 文档证据：报告“已修复/已通过”须附代码位置与测试/构建证据；未执行命令标记未验证 | R7 |

### 开发环境与历史踩坑

本机开发环境（Python/Node/PyInstaller/Inno Setup 路径与版本示例）、最小环境验证命令与历史踩坑记录见 `docs/development.md`。个人路径仅为示例，不是仓库规范。

### 协作与授权协议

- 只读审查、诊断和报告默认不修改源码、配置、数据库、安装目录或外部服务；用户明确要求修改/修复后才扩大到对应范围。
- 修改前先读取本文件、SPEC.md、ACCEPTANCE.md 及适用的子目录规则；保留已有用户修改，不使用 git reset --hard、git clean、git checkout -- 或全仓格式化清理。
- 文件编辑使用可审阅的补丁；不使用 shell 拼接写文件；Token、Cookie、API Key、密码或私钥不得写入规则文件、SPEC、ACCEPTANCE、测试快照、提交信息、构建日志或命令行参数。
- 授权分层：
  - 源码/文档修改：用户明确要求即可；
  - commit / feature branch（codex/ 前缀）/ PR：属于获准修改任务内的正常交付动作；
  - merge 到发布分支、Release、覆盖安装、真实登录、真实参与、通知外发：必须用户明确授权。
- 验证按风险选择最小充分层级：文档/配置做结构检查；局部代码做聚焦测试；跨模块接口做受影响测试；只有发布或用户明确要求才做全量测试/构建。
- Windows 长命令超时后先检查既有进程和产物，不启动重复进程；不得为了验证停止或重启用户正在使用的服务。
- 审计状态只维护在 docs/14 与 docs/13；Obsidian 01–12 为个人知识库可选镜像，不作为仓库验收依赖。

## Notes

- 版本 SSOT：`src/app_paths.__version__`（勿在 installer.iss 或文档中写死当前值）。
- 发布仓库：https://github.com/selinyi123/bil-1（origin 为 luovicter-collab/bilibinggo）。
- bil-1 是当前产品发布 SSOT；origin 旧上游仅用于历史对照，不得作为更新/安装入口。
- 详见 SPEC.md（系统规格）、ACCEPTANCE.md（验收标准）、docs/13-LAS功能迁移审计.md（迁移矩阵）和 docs/14-全量逐函数与漏洞审计-2026-08-12.md（审计底稿）。
- 多账号执行边界与 Codex↔GPT 规划循环见 docs/15-账号隔离上下文-v1.md、docs/16-Codex-GPT-规划循环.md；当前仅 `participate`/`participate_triple` 已接入不可变 AccountContext。
