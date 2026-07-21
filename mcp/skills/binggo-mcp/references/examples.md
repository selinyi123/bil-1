# Binggo MCP — 对话示例

示例展示「用户话 → 工具序列 → 对用户说什么」。工具必须串行。

---

### 例 1：查询是否登录

**用户：** 我现在登录了吗？

**工具：** `account_get`

**回复要点：** `logged_in`、昵称或未登录原因；若 `network_error` 建议 `account_refresh` 或检查网络。

---

### 例 2：扫码登录

**用户：** 帮我扫码登录

**工具：**

1. `account_get`（若已登录，先问是否重登）
2. `account_login` → **展示图片**
3. 多次 `job_get` 直到终态
4. `account_get`

**回复要点：** 引导扫码；成功后报昵称。

---

### 例 3：列出可参与活动并参与一条

**用户：** 看看最近的活动，帮我参与 dynamic_id=xxx

**工具：**

1. `account_get`
2. `activities_list`（可先不带 id 让用户选；若已给 id 可跳过或用于核对）
3. `job_participate(dynamic_id="xxx")`

**回复要点：** 终态 message / 是否成功；失败则原文。

---

### 例 4：日常更新某个源

**用户：** 更新一下 source_id=foo 这个合集

**工具：**

1. `account_get`
2. `job_refresh_source(source_id="foo")`
3. `summary_get`（可选）

---

### 例 5：用户要一键更新

**用户：** 一键更新全部活动

**工具前：** 确认用户接受耗时与风控风险（一句话即可）

**工具：** `account_get` → `job_refresh_all` → `summary_get`

---

### 例 6：拒绝通用取消

**用户：** 取消正在跑的一键更新

**工具：** 无（或仅 `job_get` 告知当前状态）

**回复要点：** 网页没有「取消当前任务」按钮；MCP 不能取消非登录 Job；登录中的扫码可用「关闭扫码」。

---

### 例 7：开定时点击

**用户：** 把定时点击打开

**工具：** `auto_status_get` → `auto_start` → `auto_status_get`

---

### 例 8：改参与文案

**用户：** 把参与文案改成「好运爆棚」

**工具：** `settings_get` → `participate_text_save(text="好运爆棚")` → `settings_get`
