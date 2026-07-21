# 方向十：MCP — 功能范围与使用规范（拍板稿）

> 状态：**已完成（收官）** — MCP + 本机 Skill 均已落地；见仓库 `mcp/`、`mcp/skills/`  
> 关联：[全栈路线图 §10](../fullstack-roadmap.md)、[方向四 API 契约](./04-api-contract.md)、[实现规范](./10-mcp-impl.md)  
> 更新：2026-07-21

本文固定三件事：

1. **产品范围**：读什么、点什么、永远不做什么  
2. **可读资源清单**（对应用户在网页上能看见的内容）  
3. **可点按钮清单** + **串行规范**

---

## 0. 一句话范围

> **MCP = 控制台可见信息的只读视图 + 网页真实业务按钮的受控点击；登录时把扫码二维码以图片交给 Agent 用户扫；只调本机 `127.0.0.1:8787`；不旁路改本地存储；工具调用严格顺序执行、禁止并发。**

| 原则 | 含义 |
|------|------|
| 可见即可读 | 用户在网页上能看到的状态/列表/摘要，MCP 都可查询 |
| 读不可直接改 | 禁止 MCP 直接写 SQLite / Cookie / `llm.env`；要改必须走「按钮」对应 API |
| 按钮可点 | **可点清单 ⊆ 网页真实控件**；禁止臆造网页没有的按钮 |
| 账号可管 | 扫码登录、账号刷新、退出登录；登录须交付二维码**图片** |
| 无意义 UI 不暴露 | 主题、收起侧栏、关确认框、导航切换等 |
| 串行 | **严格顺序执行，禁止并发**（进程内全局锁；读+写全部串行） |
| 无 confirm | 写操作**不需要** `confirm` 参数（与网页按钮同等信任） |
| Job 等待 | 除登录交图外，Job 类 tool **等到终态**再返回 |
| 非目标 | 公网 MCP、用对话完全取代 Web UI、回传 Cookie 明文、通用取消任意 Job、Skill 承担组网 |

形态约定：

- **Skill**：本机私人；开放 [Agent Skills](https://agentskills.io) 格式，见 [`mcp/skills/binggo-mcp`](../../mcp/skills/binggo-mcp/)；远端/手机走网页（如 Tailscale），不进 Skill  
- **MCP Server**：暴露 tools（读 + 点）；stdio；任意支持 MCP 的本地 Agent 均可挂载 

---

## 1. 可读资源清单（Read）

返回 JSON 结构化数据（二维码除外为图片）。敏感字段按网页同等或更严脱敏。

### 1.1 概览

| 可读内容 | 网页对应 | API |
|----------|----------|-----|
| 账号卡片摘要 | 侧栏 / 概览账号区 | `GET /api/account`、`/api/account/extras` |
| 活动统计 | 概览 stats | `GET /api/summary` |
| 参与文案 | 参与文案面板 | `GET /api/settings` |
| LLM 配置摘要（密钥脱敏） | LLM 面板 | `GET /api/settings/llm` |
| 运行时 / 项目信息 | 项目信息区 | `GET /api/runtime` |

### 1.2 数据源 / 活动 / 任务

| 可读内容 | API |
|----------|-----|
| UP 合集 / 监控同步摘要 | `GET /api/summary`、`GET /api/watch-users` |
| 活动列表（筛选与网页一致） | `GET /api/activities` |
| 三连目标预览 | `GET /api/activities/triple-targets` |
| 当前 Job | `GET /api/jobs/current` |
| 任务日志摘要 | `GET /api/diagnostics/logs` |
| 定时点击状态 | `GET /api/auto/status` |

### 1.3 登录过程

| 可读内容 | API |
|----------|-----|
| 登录相位 / `qrcode_refreshed_at` | `GET /api/jobs/current` |
| 登录二维码 **PNG 图片** | `GET /api/login/qrcode` |

### 1.4 不可读（或不可明文）

| 内容 | 原因 |
|------|------|
| Cookie / SESSDATA 明文 | 凭证 |
| LLM API Key 明文 | 凭证 |
| 任意路径文件浏览 | 超出控制台；二维码仅经 `/api/login/qrcode` |

---

## 2. 可点按钮清单（Write / Actions）

禁止旁路改库。新增 action 前必须能在 `web/frontend` 指出对应控件。

### 2.1 排除

| 项 | 原因 |
|----|------|
| 主题 / 侧栏 / 导航 / 关确认框 | 纯 UI |
| 通用「取消当前任务」 | 网页无此按钮 |
| 推测性「若 UI 有则做」 | 未落地不得进 MCP |

### 2.2 账号

| 网页控件 | 触发 |
|----------|------|
| 扫码登录 | Job `login` |
| 关闭扫码（×） | 仅 `login` 进行中时 `POST /api/jobs/cancel` |
| 刷新账号 | 重读 `GET /api/account`（及 extras） |
| 退出登录 | `POST /api/logout` |
| @「知道了」 | `POST /api/account/ack-at-unread` |

### 2.3 Job 类

| 网页按钮 | action |
|----------|--------|
| 更新监控用户动态 | `refresh_watch` |
| 刷新任务状态 | `refresh_status` |
| 一键更新 | `refresh_all` |
| 更新此源 | `refresh_source` + `source_id` |
| 单条参与 | `participate` + `dynamic_id` |
| 三连参与 | `participate_triple` |

### 2.4 其它写（配置 / 名单 / 调度 / 网络副作用按钮）

| 网页按钮 | API |
|----------|-----|
| 启动 / 停止调度 | `POST /api/auto/start`、`/stop` |
| 参与文案模式 / 保存 / 恢复默认 | settings participate-text 相关 |
| 保存 / 测试 LLM | `POST /api/settings/llm`、`/llm/test` |
| 检查更新 | `POST /api/updates/check` |
| 导出诊断包 | `GET /api/diagnostics/bundle` |
| 添加 / 删除监控用户 | watch-users POST/DELETE |

### 2.5 扫码登录（图片交付）

```text
1. account_get（已登录则勿盲目重登）
2. account_login → 启动 login Job
3. 轮询 job_get，码就绪后 account_login_qrcode → 返回 PNG 图片
4. Agent 把图片展示给用户扫码
5. 继续轮询相位；换码则重新取图
6. success → account_get；可用 account_login_cancel（关 ×）中止
```

禁止回传 Cookie。不得提供取消其它业务 Job 的工具。

---

## 3. 串行规范（无 confirm）

1. **禁止并发**：同一时刻不得并行执行多个 MCP tool 调用（实现层强制；见 impl）。  
2. **Job 互斥**：复用 `JobRunner`；忙碌则返回当前任务信息。  
3. **无 `confirm` 参数**：与网页点击同等，不再二次确认。  
4. **未登录**：需登录的写操作失败时提示可走 `account_login`（展示二维码）。  
5. 调度撞车即停等语义不变；MCP 不另造协议。

---

## 4. 架构约束

```text
任意本地 Agent（MCP 客户端）
  → MCP Server（stdio）
      → http://127.0.0.1:8787  （固定；私人使用）
          → 现有 REST API
```

- 控制台必须已在跑（B1）；MCP **不**拉起控制台。  
- **禁止** MCP 直接写库。  
- 字段名尽量与 OpenAPI 一致。

---

## 5. 验收标准（范围层）

- [x] 可读块均有对应 tool；脱敏符合 §1.4  
- [x] 可点项均能在网页指出控件；无通用取消任务  
- [x] 无 confirm 参数；全 tool 进程内串行锁  
- [x] 登录能交付二维码图片；成功/退出响应无 Cookie 明文  
- [x] 本机 Skill：`mcp/skills/binggo-mcp` + adapters；不含远端  

---

## 6. 讨论记录

| 日期 | 结论 |
|------|------|
| 2026-07-21 | 可见只读；有意义按钮可点；串行；不旁路改存储 |
| 2026-07-21 | 纳入登录/刷新/退出；对话展示二维码图片；禁回传 Cookie |
| 2026-07-21 | 可点 ⊆ 网页控件；cancel 仅关闭扫码 |
| 2026-07-21 | 实现拍板：A1 stdio；B1 控制台已运行；C 固定 8787；**D2 无 confirm**；E1 按按钮拆 tool |
| 2026-07-21 | **F1 / G2（登录先交图）/ H1**；独立 `mcp/` 落地，不改主工程 |
| 2026-07-21 | 本机 Skill：agentskills.io SSOT + 多 Agent adapters；不含远端 |
| 2026-07-21 | **收官**：MCP + Skill 实现结束；全栈路线图 1–10 全部完成 |

---

## 7. 收官

方向 10 **已完成**。入口：[`mcp/README.md`](../../mcp/README.md)、[`mcp/skills/README.md`](../../mcp/skills/README.md)、[10-mcp-impl.md](./10-mcp-impl.md)。  
全栈路线图见 [fullstack-roadmap.md](../fullstack-roadmap.md)。
