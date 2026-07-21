---
name: binggo-mcp
description: >-
  Operates the local Binggo (bilibinggo) Bilibili lottery helper console strictly
  through binggo MCP tools. Use when the user mentions Binggo/bilibinggo, local
  lottery console, 扫码登录, 活动列表, 参与/三连参与, 更新监控/刷新状态/一键更新/
  更新此源, 定时点击/启动调度/停止调度, 监控用户, 参与文案, LLM 配置, 检查更新,
  导出诊断, or asks the agent to click console buttons / show a login QR.
  Requires dashboard http://127.0.0.1:8787 and MCP server name binggo.
  Do NOT use for Tailscale/remote phone networking, Funnel, changing Binggo
  src/web code, inventing non-UI actions, reading Cookie/llm.env files, or
  theme/sidebar-only UI.
license: Proprietary. See repository LICENSE if present.
compatibility: >-
  Requires Binggo MCP (stdio) + local dashboard at http://127.0.0.1:8787.
  Agent Skills format (agentskills.io). Any client that loads SKILL.md and can
  call MCP tools.
metadata:
  author: bilibinggo
  version: "0.2.0"
  scope: local-private
  mcp_server: binggo
  api_base: http://127.0.0.1:8787
---

# Binggo MCP — 本机私人操作手册

通过 **MCP `binggo`** 操作本机已运行的 Binggo 网页控制台。  
本 Skill 是扩展能力，**禁止**修改仓库 `src/`、`web/` 等业务实现。

> 脚本/参考路径均相对本 Skill 目录。详细表与长流程按需打开 `references/`，不要一次性全部读入。

## 何时启用 / 何时不用

| 启用 | 不用 |
|------|------|
| 用户要查登录、活动、监控、调度、文案、LLM | 只谈 Tailscale / 手机浏览器远程（已有网页通道） |
| 用户要「帮我点控制台某个按钮」 | 要改 Binggo 源码、加网页没有的按钮 |
| 用户要 Agent 展示登录二维码并完成扫码 | 要读 Cookie / 明文 API Key / 任意文件浏览 |

## 决策树（先选路径）

```text
用户意图
├─ 连不上 / 工具报连接失败？
│    → 让用户启动: python scripts/run_dashboard.py
│    → 确认 MCP binggo 已配置（见仓库 mcp/README.md）
│    → 禁止臆造账号或活动数据
│
├─ 只要信息（查状态/列表）？
│    → 「只读路径」：account_get / summary_get / activities_list / …
│
├─ 要登录或换号？
│    → 「扫码登录路径」（必须把 PNG 展示给用户）
│
├─ 要更新数据 / 参与 / 调度 / 改设置？
│    → 先读状态 → 确认已登录（若需要）→ 一次一个写工具 → 再读验证
│
└─ 用户要「取消正在跑的更新/参与任务」？
     → 拒绝：网页没有通用取消；仅登录可用 account_login_cancel
```

## 硬性约束（违反即错误用法）

1. **全串行**：同一时刻只调用一个 MCP tool；等返回后再调用下一个。禁止并行 tool。
2. **可点 ⊆ 网页真实按钮**：禁止臆造 action；禁止通用 `job_cancel`。
3. **登录取消特例**：仅 `account_login_cancel`（等同关扫码 ×）。
4. **密钥不出对话**：不索要、不回显 Cookie / SESSDATA / LLM API Key 明文。
5. **不改主工程**：不为“方便 MCP”去改 `src/`、`web/`。
6. **Job 阻塞**：`job_*`（除登录交图）会等到任务终态才返回；可能很久。
7. **一键更新慎用**：`job_refresh_all` 仅当用户明确要求「一键更新」；日常用 `job_refresh_source`。

## 前置检查清单

复制并勾选：

```text
- [ ] 本机 http://127.0.0.1:8787 可开（dashboard 已跑）
- [ ] Agent 已挂载 MCP：binggo
- [ ] 需要写操作时：account_get.logged_in == true（否则先登录流程）
- [ ] job_get 无意外 running（或接受写工具会先等其结束）
```

## 默认节奏

```text
读（按需）→ 写（单个 tool）→ 读验证
```

向用户汇报时建议结构：

```markdown
### 结果
- 做了什么（工具名）
- 关键/终态（success|error|…）与关键 message
- 下一步建议（若有）
```

## 扫码登录（低自由度 — 必须按序）

```text
进度:
- [ ] 1. account_get（已登录且用户未要求重登 → 停止并说明）
- [ ] 2. account_login → 得到 PNG → **立刻在对话中展示图片**
- [ ] 3. 请用户用哔哩哔哩 App 扫码并确认
- [ ] 4. 串行 job_get，直到 state ∈ {success, error, cancelled, interrupted}
- [ ] 5. 若 qrcode_refreshed_at 变化 → account_login_qrcode → 再展示新图
- [ ] 6. 用户放弃 → account_login_cancel（仅此）
- [ ] 7. success 后 account_get 确认昵称
```

**Gotchas**

- `account_login` 在码就绪后就返回；**登录 Job 仍在跑**，必须继续 `job_get`。
- 只返回 JSON 不展示图 = 失败用法。
- `account_refresh` ≠ 扫码；只是重拉账号接口。

## 常用写操作速查

| 用户说法 | 串行调用 |
|----------|----------|
| 登录了吗 / 账号怎样 | `account_get` |
| 概览 / 统计 | `summary_get` |
| 有哪些活动 | `activities_list`（可加筛选） |
| 更新某个 UP 合集 | `job_refresh_source(source_id=…)` |
| 更新监控动态 | `job_refresh_watch` |
| 刷新任务状态 | `job_refresh_status` |
| 一键更新全部 | 仅明确要求时 `job_refresh_all` |
| 参与某条 | `activities_list` → `job_participate(dynamic_id=…)` |
| 三连参与 | `triple_targets_get` → 确认 → `job_participate_triple` |
| 开/关定时点击 | `auto_status_get` → `auto_start` / `auto_stop` → 再读 |
| 加/删监控 | `watch_users_list` → add/remove → 再 list |
| 改参与文案 | `settings_get` → `participate_text_save` / mode / reset |
| LLM 保存/测试 | `llm_settings_get` → save/test（勿回显 Key） |
| 检查更新 | `updates_check` |
| 导出诊断 | `diagnostics_export`（勿把敏感全文贴进对话） |

## Gotchas（高频踩坑）

- **Dashboard 只听 127.0.0.1:8787**：MCP 也写死该地址；装包 8181 / Tailscale 网页与本 Skill 无关。
- **未登录写操作**：API 会失败；先走登录流程，不要改代码绕过。
- **并行点按钮**：MCP 层串行锁 + Job 互斥；仍禁止你并发发起多个 tool。
- **“取消更新”**：没有对应网页按钮 → 明确拒绝并解释。
- **diagnostics / LLM**：响应或导出可能含敏感信息 → 摘要即可。
- **participate 文案 mode**：`custom` vs `random_comment` 决定保存的是正文还是兜底；不确定先 `settings_get`。

## 反馈环（质量）

每次写操作后：

1. 读返回 JSON 的 `error` / `job.state` / `message`
2. 失败 → 用原文告诉用户；若是未登录/LLM 未就绪，给出下一步 tool
3. 成功 → 再读一次相关只读工具核对（不要声称未验证的结果）

## 按需深入阅读（progressive disclosure）

| 需要时再读 | 文件 |
|------------|------|
| 全工具参数与返回约定 | [references/tools.md](references/tools.md) |
| 完整调用链与边界 | [references/workflows.md](references/workflows.md) |
| 报错对照与排障 | [references/troubleshooting.md](references/troubleshooting.md) |
| 对话示例（输入→工具序列） | [references/examples.md](references/examples.md) |
| 挂到 Cursor/Claude/Codex 等 | [../adapters/README.md](../adapters/README.md) |

## 范围外

- Tailscale Serve / Funnel / 手机 Agent 远程 MCP
- 主题、侧栏、导航等纯 UI
- 直接写 SQLite、Cookie 文件、`llm.env`
- 修改 Binggo 应用源码
