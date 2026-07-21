"""Agent-facing server instructions (MCP protocol instructions field)."""

from __future__ import annotations

from binggo_mcp.client import BASE_URL

INSTRUCTIONS = f"""
你正在使用「Binggo 本地控制台」MCP：只操作本机已运行的网页控制台能力，不直接改数据库/Cookie 文件。

## 前置条件
- 控制台必须已在跑，且地址固定为 {BASE_URL}（开发：python scripts/run_dashboard.py）。
- 连不上时先让用户启动控制台，不要臆造数据。

## 硬性约束（必须遵守）
1. **全串行**：同一时刻只能调用一个 tool；禁止并行/批量并发调多个 tool。上一次返回后再调下一次。
2. **可点范围 = 网页真实按钮**：没有「取消任意任务」；只能用 account_login_cancel 关闭扫码登录。
3. **无 confirm 参数**：写操作与网页点击同等，但仍应先读状态再写，避免误操作。
4. **禁止索要或回显**：Cookie / SESSDATA / LLM API Key 明文。密钥相关只用脱敏摘要。
5. **不要**用本 MCP 改主题、侧栏、导航等纯 UI。

## 推荐节奏
1. 先读：account_get / summary_get / job_get / auto_status_get（按需）。
2. 若需登录：走「扫码登录流程」（见下），成功后再写。
3. 写操作（job_* / auto_* / settings / watch）：一次一个；job_* 会阻塞到该任务结束才返回。
4. 写完再读验证（job_get / account_get / activities_list 等）。

## 扫码登录流程（重要）
1. account_get：已登录则勿盲目重登（除非用户明确要求换号/重登）。
2. account_login：等待二维码就绪后返回 **PNG 图片**；此时登录 Job 仍在服务端进行。
3. 把图片展示给用户，请其用哔哩哔哩 App 扫码并确认。
4. 串行轮询 job_get，查看 result.login_phase / state，直到 success 或 error。
5. 若二维码刷新（qrcode_refreshed_at 变化）：再调 account_login_qrcode 取新图并展示。
6. 用户要放弃扫码：account_login_cancel（等同网页点 ×）。**不能**取消其它业务 Job。
7. 成功后 account_get 确认昵称。

## Job 类工具
- job_refresh_watch / job_refresh_status / job_refresh_all / job_refresh_source /
  job_participate / job_participate_triple：调用后会 **等到任务终态** 再返回（可能很久，尤其 refresh_all）。
- 若控制台里已有任务在跑，会先等待其结束再启动（仍可能因服务端互斥失败，把错误原样告诉用户）。
- 日常优先 job_refresh_source（单源）；job_refresh_all 更重、更易触发风控，仅在用户明确要一键更新时用。

## 账号与其它写操作
- account_refresh：只是重新拉取账号接口，不是重新扫码。
- account_logout：退出登录；之后需登录的写操作会失败，应引导重新 account_login。
- auto_start / auto_stop：定时点击调度；撞车即停等语义与网页一致，不要并行点其它 Job。
- participate_text_* / llm_settings_* / watch_user_* / updates_check / diagnostics_export：
  对应网页同名按钮；diagnostics_export 的 text 可能含敏感信息，不要在对话里完整粘贴。

## 读工具速查
- account_get / account_refresh：登录态与账号卡片
- summary_get：概览统计与源摘要
- activities_list / triple_targets_get：活动与三连目标
- watch_users_list：监控名单
- settings_get / llm_settings_get / runtime_get：设置与运行时
- job_get / job_logs_get / auto_status_get：任务与调度状态
- account_login_qrcode：仅取当前登录二维码图（需已有 login 流程）
""".strip()
