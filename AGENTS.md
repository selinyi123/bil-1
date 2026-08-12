# AGENTS.md

Binggo —— 本机（local-first）B 站抽奖助手：自动发现抽奖活动、Web 控制台浏览、定时自动参与。Python 3.12 + FastAPI + SQLite + Vite/TS 前端。

## 目标（Product Goal）

- 单机闭环：数据源发现 → 活动库 → 参与 → 中奖提醒 → 清理，全程本机 SQLite，不上云。
- 安全优先：只删 Binggo 自己创建的东西、凭据绝不出本机、local-first 不产生意外副作用。
- 长期稳定：web 服务形态 + 定时调度，对抗 B 站风控（限流/WBI/幂等）。

## 仓库结构

```
binggo_launcher.py       入口：launcher 守护 serve 子进程（--serve 跑 dashboard_server）
src/                    领域层（不依赖 web）
  bilibili_*.py         B 站客户端：WBI 签名、限流、身份 resolve_effective_uid
  participation*.py     参与链路：五连/预约、dry_run、单事务持久化
  lottery_actions.py    动作执行（like/follow/favorite/repost/comment）、ActionResult(extra)
  sources/              DS-1~10 数据源（fingerprint 增量、checkpoint）
  source_settings.py    DS-8/9/10 Web 受控配置（file:// 仅限 BINGGO_HOME、URL 脱敏）
  db/                   SQLite（schema v3）、activity_store、participation_store
  clear_follows.py      清理（exact ownership：只删 created_dynamic_id 匹配的转发）
  draw_check.py         中奖深检（送达确认后才 mark read）
  notify.py             15 渠道通知（_http_ok 业务码校验、飞书官方签名）
  app_paths.py          路径解析 + 版本 SSOT __version__
web/                    FastAPI：app.py、actions.py、product_routes.py、job_runner.py、
                        auto_scheduler.py、local_guard.py（Host/Origin）、schemas/
web/frontend/           Vite + TS（settings 页、数据源面板、jobs/account/activities）
docs/                   fullstack-roadmap、pipeline-redesign、plans/（方向拍板）、
                        13-LAS功能迁移审计.md（LAS 迁移矩阵与 gap）
tests/                  97 个 pytest 文件（isolated_home fixture 隔离）
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
- **参与副作用**：`dry_run` 必须贯穿到底层（HTTP → `participate_activity`）；`follow` 失败后不创建/移动关注分区；内部业务失败**绝不 set cancel_event**（终态 `error`/`error_kind=business_partial`）。
- **schema**：未来版本 DB 在任何写操作前 hard fail，绝不自动降级；`init_db` 顺序 = 读版本→hard fail→迁移→create_all。
- **Web mutation**：Job 运行中 fail-closed（`_reject_mutation_while_job_running`）；不得绕过 Host/Origin 校验。
- **事务**：参与结果三表（actions/participations/activities）必须同一 session 事务。
- **ORM**：`session_scope` 块内读取字段，块外访问会 DetachedInstanceError（曾致台账静默空集）。
- **测试**：新增/修改行为必须带不变量测试（见 ACCEPTANCE.md）；测试用 `isolated_home` fixture 隔离 BINGGO_HOME 与 DB。

## Notes

- 版本 SSOT：`src/app_paths.__version__`（勿在 installer.iss 手写）；当前 v5.1.0。
- 发布仓库：https://github.com/selinyi123/bil-1（origin 为 luovicter-collab/bilibinggo）。
- 详见 SPEC.md（系统规格）与 ACCEPTANCE.md（验收标准）；LAS 迁移状态见 docs/13-LAS功能迁移审计.md。
