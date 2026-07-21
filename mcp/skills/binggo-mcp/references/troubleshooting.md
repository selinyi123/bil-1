# Binggo MCP — 排障

## 连接类

| 现象 | 处理 |
|------|------|
| 无法连接 / connection refused | 用户执行 `python scripts/run_dashboard.py`；确认 `127.0.0.1:8787` |
| ModuleNotFoundError: binggo_mcp | MCP 配置缺 `PYTHONPATH=…/mcp` 或未 `pip install -e mcp/` |
| MCP 未出现在 Agent | 检查 mcp.json 的 `type: stdio`、绝对路径 python、cwd |

## 登录类

| 现象 | 处理 |
|------|------|
| 二维码尚未生成 | 先 `account_login`，稍后再 `account_login_qrcode` |
| 一直 waiting | 请用户确认已扫码；检查是否换码需重新展示图 |
| 登录前已终态 error | 读 `message`；可 `account_login` 重试 |
| cancel 报非 login | 当前不是登录任务；不能当通用取消用 |

## 业务写失败

| 典型 message / code | 处理 |
|---------------------|------|
| 请先扫码登录 | W1 登录流程 |
| LLM 未配置 / 未测试 | W12 |
| 已有任务正在运行 / JOB_BUSY | `job_get` 说明当前任务；等其结束或告知用户 |
| 活动 ID / 数据源 ID 无效 | 重新 `activities_list` / `summary_get` 核对 id |
| 风控 / 网络类 | 原文转述；不要自行重试刷屏 `job_refresh_all` |

## 调度类

| 现象 | 处理 |
|------|------|
| fatal 停机 | `auto_status_get` 读原因；用户理解后再 `auto_start` |
| 与 Job 冲突 | 先让 Job 结束或停止调度，再操作 |

## Agent 行为自检

- [ ] 是否并行调了多个 tool？→ 立即改为串行
- [ ] 是否展示了登录 PNG？→ 否则用户无法扫码
- [ ] 是否在未验证时声称“已成功”？→ 补一次只读
- [ ] 是否把诊断包全文贴出？→ 改为摘要
