# 方向十：MCP — 落地实现规范

> 状态：**已落地（收官）** — 独立 `mcp/` 包；不修改现有业务代码  
> 拍板依据：[10-mcp.md](./10-mcp.md)  
> 依赖：方向四稳定 REST；控制台已在本机运行  
> 更新：2026-07-21

本文是编码前规范：传输、基址、tool 命名表、串行实现、二维码图片、目录、测试与分期。

---

## 0. 已拍板（不可违背）

| ID | 结论 |
|----|------|
| A | **A1** stdio MCP Server |
| B | **B1** 控制台必须已运行；MCP 不拉起进程 |
| C | 基址固定 **`http://127.0.0.1:8787`**（私人使用；不做端口发现 / 环境变量覆盖） |
| D | **D2** 写操作**无** `confirm` 参数 |
| E | **E1** 按网页按钮拆开独立 tool |
| F* | Skill **暂缓**；面向任意 MCP 客户端，不绑 Cursor |
| G* | 二维码交付：**MCP image content（PNG）** |
| H* | 可点 ⊆ 网页真实控件；通用取消 Job **不做** |

\* 来自范围讨论，与 A–E 同等约束。

---

## 1. 架构

```text
Agent (任意 MCP client)
  │ stdio
  ▼
mcp/binggo_mcp/  (本仓库 Python 包)
  │ httpx → http://127.0.0.1:8787
  ▼
Binggo Dashboard (已运行)
  └── /api/* 现有契约
```

| 约束 | 说明 |
|------|------|
| 薄封装 | tool 只转发 REST；不写 SQLite / Cookie / llm.env |
| 宕机提示 | 连不上 8787 → 明确错误：「请先启动控制台（开发：`python scripts/run_dashboard.py`）」 |
| 错误透传 | 尽量保留 API 的 `error.code` / `error.message` |

---

## 2. Tool 命名表（权威）

命名约定：`领域_动词`；读用 `*_get` / `list_*`；写与网页文案对应。

### 2.1 Read

| Tool | 网页对应 | HTTP |
|------|----------|------|
| `account_get` | 账号卡片 / 刷新账号读结果 | `GET /api/account` + 可选 extras |
| `summary_get` | 概览统计 + 源摘要 | `GET /api/summary` |
| `settings_get` | 参与文案等设置展示 | `GET /api/settings` |
| `llm_settings_get` | LLM 面板（脱敏） | `GET /api/settings/llm` |
| `runtime_get` | 项目信息 | `GET /api/runtime` |
| `watch_users_list` | 监控名单 + 同步状态 | `GET /api/watch-users` |
| `activities_list` | 活动表（筛选参数与网页 query 对齐） | `GET /api/activities` |
| `triple_targets_get` | 三连目标条 | `GET /api/activities/triple-targets` |
| `job_get` | 顶部进度 / 结果 | `GET /api/jobs/current` |
| `job_logs_get` | 任务日志坞 | `GET /api/diagnostics/logs` |
| `auto_status_get` | 定时点击坞状态 | `GET /api/auto/status` |
| `account_login_qrcode` | 扫码弹窗二维码图 | `GET /api/login/qrcode` → **返回 image/png** |

### 2.2 Account actions

| Tool | 网页控件 | HTTP / Job |
|------|----------|------------|
| `account_login` | `#sidebar-login` 扫码登录 | `POST /api/jobs` `{action:"login"}` |
| `account_login_cancel` | `#qrcode-close` 关闭扫码 | 仅当前为 `login` 时 `POST /api/jobs/cancel`；否则拒绝 |
| `account_refresh` | `#sidebar-refresh-account` | 同 `account_get`（语义：刷新；实现可复用） |
| `account_logout` | `#sidebar-logout` | `POST /api/logout` |
| `account_ack_at_unread` | `#account-at-ack-btn` 知道了 | `POST /api/account/ack-at-unread` |

### 2.3 Job actions（各一 tool）

| Tool | 网页 | Body |
|------|------|------|
| `job_refresh_watch` | 更新监控用户动态 | `action=refresh_watch` |
| `job_refresh_status` | 刷新任务状态 | `action=refresh_status` |
| `job_refresh_all` | 一键更新 | `action=refresh_all` |
| `job_refresh_source` | 更新此源 | `action=refresh_source`, `source_id` |
| `job_participate` | 参与 | `action=participate`, `dynamic_id` |
| `job_participate_triple` | 三连参与 | `action=participate_triple` |

成功体与现网一致，期望含 `{ok, job}`；忙碌时透传 Job 互斥错误。

### 2.4 其它写

| Tool | 网页 | HTTP |
|------|------|------|
| `auto_start` | 启动调度 | `POST /api/auto/start` |
| `auto_stop` | 停止调度 | `POST /api/auto/stop` |
| `participate_text_save` | 保存文案 | settings participate-text API（与前端一致） |
| `participate_text_reset` | 恢复默认 | 与前端一致 |
| `participate_text_mode_set` | 切换模式 | 与前端一致 |
| `llm_settings_save` | 保存配置 | `POST /api/settings/llm` |
| `llm_settings_test` | 测试连接 | `POST /api/settings/llm/test` |
| `updates_check` | 检查更新 | `POST /api/updates/check` |
| `diagnostics_export` | 导出诊断包 | `GET /api/diagnostics/bundle`（返回元数据；不把密钥打进对话） |
| `watch_user_add` | 添加用户 | `POST /api/watch-users` |
| `watch_user_remove` | 删除用户 | `DELETE /api/watch-users/{mid}` |

### 2.5 明确不做的 tool

- 通用 `job_cancel`  
- 主题 / 侧栏 / 导航  
- 任意 `http_proxy` / 原始 `call_api`  
- 读 Cookie / 明文 Key  

---

## 3. 串行执行（强制）

> 用户要求：**严格顺序，不能并发**；且无 confirm。

### 3.1 MCP 进程内（必做）

- 维护一把 **全局 asyncio 锁**：**全部 tool**（读+写）同一时刻只执行一个（**H1**）。  
- 客户端若并行发起：后到的调用在锁上等待。  
- Job 类仍依赖服务端 `JobRunner` 互斥。

### 3.2 跨进程（**F1**）

只保证单 MCP 进程内串行；不设跨进程文件锁。私人单 Agent 使用即可。

### 3.3 Job 类工具返回时机（**G2**）

- 除登录扫码特例外：Job 类 tool **启动后轮询直至终态**（`success` / `error` / `cancelled` / `interrupted`）再返回。  
- **登录例外**：必须先把二维码图片交给用户才能扫码，故 `account_login` 在二维码就绪后即返回图片；登录是否成功由后续串行的 `job_get` 观察。换码用 `account_login_qrcode`。

---

## 4. 二维码图片

| 项 | 规范 |
|----|------|
| 获取 | `account_login_qrcode` → `GET /api/login/qrcode` |
| 交付 | MCP 标准 **image** 内容块（`mimeType: image/png` + 二进制/base64，按所用 SDK） |
| 附带 JSON | 可同时带短文本：`login_phase`、`qrcode_refreshed_at`、`message`（来自 `job_get`） |
| 未生成 | HTTP 404 → tool 错误：「二维码尚未生成，请先 account_login 并等待」 |
| 换码 | `qrcode_refreshed_at` 变化后再次调用本 tool，重新发图 |

`account_login` 本身返回 JSON（job 已创建）；**不**在 login 工具里塞图，避免与「码未就绪」竞态；由 Agent：`login` → 轮询 → `account_login_qrcode`。

---

## 5. 目录与依赖

```text
mcp/
  README.md
  requirements.txt
  pyproject.toml
  binggo_mcp/
    __init__.py
    __main__.py
    server.py      # FastMCP stdio + 全部 tools
    client.py      # httpx → 127.0.0.1:8787
    serial.py      # 全局锁 H1
    jobs.py        # Job 启动与等到终态 G2；登录先交图
```

安装：`pip install -r mcp/requirements.txt` 或 `pip install -e mcp/`。  
入口：`python -m binggo_mcp`（需 `PYTHONPATH=mcp` 或 editable 安装）。

**红线：** 本扩展不得修改 `src/`、`web/`、现有测试与业务逻辑。

---

## 6. 客户端挂载（通用示例）

任意支持 MCP stdio 的客户端，配置形如：

```json
{
  "mcpServers": {
    "binggo": {
      "command": "python",
      "args": ["-m", "binggo_mcp"],
      "cwd": "<本仓库根目录>"
    }
  }
}
```

（字段名因客户端而异；`mcp/README.md` 写 2～3 个常见客户端对照，**不**做成 Cursor-only。）

前置：本机已 `python scripts/run_dashboard.py`（或等价）监听 **8787**。

---

## 7. 测试计划

| 项 | 期望 |
|----|------|
| 控制台未启动 | 任意 tool → 友好「请先启动」 |
| 串行 | 并发两个 mock 调用 → 不重叠执行 |
| Job 互斥 | running 时再 `job_refresh_status` → 忙碌错误含当前 action |
| 登录出图 | login → 轮询 → qrcode tool 返回 png image |
| login_cancel | 非 login Job 时拒绝 |
| logout / login 成功 | 响应无 Cookie 字段 |
| 对照表 | 每个 action tool 有前端控件锚点注释或单测清单 |

---

## 8. 边角拍板（已定）

| 项 | 结论 |
|----|------|
| **F1** | 仅单 MCP 进程内串行；无跨进程文件锁 |
| **G2** | Job 类 tool 等到终态再返回；**登录例外**见 §3.3（先交二维码图） |
| **H1** | 全部 tool（读+写）同一把锁，不能并发 |

编码开始条件：✅ 已满足。独立目录 `mcp/`，**禁止修改** `src/` / `web/` / 现有测试与业务逻辑。

---

## 9. 分期

| 阶段 | 内容 |
|------|------|
| P0–P4 | 一次落地于 `mcp/`：脚手架、全 Read、全 Job（含等到终态）、账号/设置/调度、README |

---

## 10. 讨论记录

| 日期 | 内容 |
|------|------|
| 2026-07-21 | A1 B1 C=8787 D2 E1；图片交付；Skill 暂缓 |
| 2026-07-21 | F1 / G2（登录先交图）/ H1；开始在 `mcp/` 编码且不改现有工程 |
