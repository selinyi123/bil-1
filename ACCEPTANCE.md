# Binggo 验收标准（ACCEPTANCE）

> 交接文档（2026-08 · v5.1.0）。验收分四层：构建、测试、功能、安全与不变量。
> 每次改动（尤其涉及身份/参与/清理/凭据/数据源）必须通过对应不变量验收。

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
| T1 | 全量 pytest | **632 passed, 1 skipped, 0 failed**（新改动不得低于此基线） |
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
| F7 | 清理 clear_follows | 默认预演；只删 `created_dynamic_id` 匹配的转发；手动转发不删；白名单保护 |
| F8 | 中奖深检 | 至少一渠道送达后才 mark DM read；全部失败保留未读；`delivered`/`acknowledged` 准确 |
| F9 | 数据源管理（Web） | DS-8/9 typed 保存；DS-10 脱敏增删；file:// 仅限 BINGGO_HOME；Job 运行中 mutation 被拒 |
| F10 | 通知 | 渠道业务码错误不记"已发送"；飞书签名官方算法；配置凭据不回显 |

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
| I8 | **通知确认** | provider 未确认成功（HTTP≥400 或业务码失败/无法解析）绝不进入 `sent` |
| I9 | **dry_run 贯穿** | HTTP `dry_run=true` 必须传到底层（`participate_activity(dry_run=True, persist=False)`），预演零副作用 |
| I10 | **读函数无写副作用** | `load_payload` 纯读；seed/过期更新走显式函数 |
| I11 | **事务原子** | 参与结果三表（actions/participations/activities）同一事务；crash 不产生"已参加"不一致 |
| I12 | **Web 防护** | Host 非回环 / mutation 带非本机 Origin → 403（LocalControlPlaneGuard） |
| I13 | **数据源沙箱** | Web 新增 file:// 仅限 BINGGO_HOME（percent-encoding 解码后校验） |
| I14 | **重试语义** | WBI key 获取失败与 HTTP 失败同一 retry 语义；业务码错误不重试 |

## 5. 发布验收

| # | 检查项 |
|---|---|
| R1 | `src/app_paths.__version__` 已 bump（SSOT）且 git tag 对应 |
| R2 | 全量测试通过（T1）后 commit；推送 `selinyi123/bil-1` main |
| R3 | build.ps1 产出 Setup + Portable，版本号与 __version__ 一致 |
| R4 | 覆盖安装后 8181 可用、功能冒烟（F1/F6 至少） |
| R5 | 知识库/文档同步（AGENTS.md、SPEC.md、docs/13 审计、Obsidian 更新小节） |

## 6. 回归提醒（踩坑记录）

- ORM：`session_scope` 块外访问 row 属性会 DetachedInstanceError（曾致 clear_follows 台账静默空集）——读取必须在块内。
- PowerShell 转义：`git rev-parse 'hash^{tree}'` 需单引号；python 内联字符串注意引号。
- GitHub 直连可能间歇性被阻断：`gh api` 可重建推送（内容一致，commit sha 因日期归一化不同）。
- 测试隔离：新模块引用静态 `DATA_DIR` 时须确认 `isolated_home` fixture 已覆盖（conftest 模块列表）。
- 前端构建产物 `web/static/dist` 被 gitignore，改前端源码后需本地 build 才生效。
