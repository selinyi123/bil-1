# Binggo MCP — 工具参考

需要参数细节时再读本文件。全部经 MCP → `http://127.0.0.1:8787`。

约定：

- **串行**：任意时刻只跑一个 tool
- **写操作无 confirm 参数**（与网页点击同等）
- Job 类：`job_*` 会阻塞到终态（`success` / `error` / `cancelled` / `interrupted`），登录交图除外

---

## 只读

### `account_get`

- **参数**：`include_extras`（bool，默认 true）
- **用途**：登录态、昵称、过期/网络提示、@ 相关字段
- **之后**：未登录且要写 → 登录流程；已登录 → 可写

### `account_refresh`

- 语义同「刷新账号」：重拉 account（±extras），**不是**扫码

### `summary_get`

- 概览统计、源摘要、当前 job 快照
- 适合开场了解全局

### `settings_get`

- 参与文案、模式、默认文案字段
- 改文案前先读，确认 `participate_text_mode`

### `llm_settings_get`

- 是否配置、是否测试通过、模型名、Key **遮罩**
- 禁止把遮罩还原成明文或向用户套 Key（除非用户主动要配置并自行提供）

### `runtime_get`

- 版本、数据目录、runtime 标签

### `watch_users_list`

- 监控名单 + 同步窗口/上次同步等

### `activities_list`

- **常用参数**（均可选）：`status`, `type`, `draw`, `draw_window`, `q`, `sort`, `order`, `page`, `page_size`
- 参与前用本工具拿到 `dynamic_id`

### `triple_targets_get`

- 三连目标预览；参数与活动筛选类似（无分页或较少）
- `job_participate_triple` 前建议先读

### `job_get`

- 当前 job：`state`, `action`, `message`, `progress_*`, `result`（含 `login_phase`, `qrcode_refreshed_at`）
- 登录过程中的主轮询工具

### `job_logs_get`

- **参数**：`job_id`（可选）, `limit`（默认 200）
- 任务日志坞摘要

### `auto_status_get`

- 定时点击：相位、倒计时、fatal、是否运行中

### `account_login_qrcode`

- 返回 **PNG 图片** + 短 JSON
- 仅在登录流程中、码已生成后使用；换码时再调

---

## 账号写

| Tool | 网页 | 要点 |
|------|------|------|
| `account_login` | 扫码登录 | 返回 PNG；Job 继续；见 workflows 登录 |
| `account_login_cancel` | 关扫码 × | **仅** `action=login` 进行中 |
| `account_logout` | 退出登录 | 之后需登录的写会失败 |
| `account_ack_at_unread` | @「知道了」 | 参数 `current`（当前未读数） |

---

## Job 写（阻塞到终态）

| Tool | 参数 | 何时用 |
|------|------|--------|
| `job_refresh_watch` | — | 更新监控用户动态 |
| `job_refresh_status` | — | 刷新开奖/参与状态 |
| `job_refresh_all` | — | **仅用户明确要一键更新**；重、易风控 |
| `job_refresh_source` | `source_id` | 日常更新单源（推荐） |
| `job_participate` | `dynamic_id` | 单条参与 |
| `job_participate_triple` | — | 三连参与 |

行为细节：

- 若已有 running job，实现会先等待其结束再启动（仍可能因服务端互斥失败）
- 超时/失败时把 MCP/API 错误原文转述用户

---

## 其它写

| Tool | 参数 | 说明 |
|------|------|------|
| `auto_start` / `auto_stop` | — | 定时点击；先 `auto_status_get` |
| `participate_text_save` | `text`, 可选 `mode` | mode 缺省则读当前设置；`random_comment` 写兜底 |
| `participate_text_reset` | — | 按当前模式恢复默认 |
| `participate_text_mode_set` | `mode`: `custom` \| `random_comment` | |
| `llm_settings_save` | `api_key`, `base_url`, `model_name` | Key 空=不改已有；勿回显 Key |
| `llm_settings_test` | 同上 | 测试连接 |
| `updates_check` | — | 查 GitHub Release |
| `diagnostics_export` | 可选 `job_id` | 返回 filename/text；**勿全文粘贴密钥** |
| `watch_user_add` | `mid` int | |
| `watch_user_remove` | `mid` int | |

---

## 明确不存在的能力

- 通用取消任意 Job
- 主题 / 侧栏 / 导航
- 原始 Cookie 文件读取
- 任意路径文件浏览
- 旁路写库
