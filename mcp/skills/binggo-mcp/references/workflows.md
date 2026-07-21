# Binggo MCP — 完整工作流

所有步骤 **串行**。复制清单跟踪进度。

---

## W1 — 扫码登录

```text
- [ ] account_get
- [ ] 若 logged_in 且用户未要求重登：说明现状并结束
- [ ] account_login → 展示 PNG
- [ ] 提示：用哔哩哔哩 App 扫码确认
- [ ] 循环 job_get（每次单独调用）
      - success → 跳出
      - error / cancelled / interrupted → 报告 message，询问是否重试
      - running + qr 刷新 → account_login_qrcode → 展示新图 → 继续
- [ ] 用户说取消 → account_login_cancel → 结束
- [ ] account_get 确认 uname
```

**不要**：登录未完成就去跑 `job_participate` / `refresh_*`。

---

## W2 — 只读健康检查

```text
- [ ] account_get
- [ ] summary_get
- [ ] job_get
- [ ] auto_status_get
```

输出：是否登录、概览数字、当前 job、调度是否运行/fatal。

---

## W3 — 更新单源（推荐日常）

```text
- [ ] account_get（需登录）
- [ ] summary_get 或既有 source_id
- [ ] job_refresh_source(source_id=…)
- [ ] summary_get 或 activities_list 验证
```

---

## W4 — 更新监控动态

```text
- [ ] account_get
- [ ] job_refresh_watch
- [ ] watch_users_list 或 summary_get
```

---

## W5 — 刷新任务状态

```text
- [ ] account_get
- [ ] job_refresh_status
- [ ] activities_list（可选）
```

---

## W6 — 一键更新（高成本）

仅当用户明确说「一键更新」「全部更新」等：

```text
- [ ] 口头确认风险（耗时长 / 风控）
- [ ] account_get + 可选 llm_settings_get（若流水线依赖 LLM）
- [ ] job_refresh_all
- [ ] summary_get
```

---

## W7 — 单条参与

```text
- [ ] account_get（需登录）
- [ ] activities_list → 选定 dynamic_id
- [ ] （可选）向用户确认奖品/链接
- [ ] job_participate(dynamic_id=…)
- [ ] 根据返回 result / activities_list 汇报
```

---

## W8 — 三连参与

```text
- [ ] account_get
- [ ] triple_targets_get → 向用户展示将参与的目标
- [ ] 用户确认
- [ ] job_participate_triple
- [ ] 汇报结果
```

---

## W9 — 定时点击

```text
- [ ] auto_status_get
- [ ] auto_start 或 auto_stop
- [ ] auto_status_get
```

撞车即停等语义与网页一致；把 fatal/message 原样说明。

---

## W10 — 监控用户增删

```text
- [ ] account_get
- [ ] watch_users_list
- [ ] watch_user_add(mid=…) 或 watch_user_remove(mid=…)
- [ ] watch_users_list
```

---

## W11 — 参与文案

```text
- [ ] account_get
- [ ] settings_get → 看 participate_text_mode
- [ ] 切换模式？ participate_text_mode_set(mode=…)
- [ ] 保存？ participate_text_save(text=…, mode?=…)
- [ ] 恢复默认？ participate_text_reset
- [ ] settings_get 验证
```

---

## W12 — LLM 配置

```text
- [ ] account_get
- [ ] llm_settings_get
- [ ] 用户提供字段 → llm_settings_save（勿在回复中重复明文 Key）
- [ ] llm_settings_test
- [ ] llm_settings_get 看 test_passed
```

---

## W13 — 检查更新 / 诊断

```text
updates_check → 摘要版本对比

diagnostics_export → 只报告 filename / 是否成功；
不要把 text 里可能含密钥的内容完整贴进聊天
```

---

## 边界与拒绝话术（建议）

| 用户要求 | 回应要点 |
|----------|----------|
| 取消正在跑的一键更新 | 网页无此按钮；MCP 不能通用取消；可等其结束或去网页侧处理登录取消以外的情况 |
| 帮我改源码让并发 | 拒绝；Skill/MCP 扩展不改主工程 |
| 把 Cookie 发我 | 拒绝 |
| 手机 Agent 远程点按钮 | 本 Skill 不覆盖；用 Tailscale 网页或另做远程 MCP（未在本 Skill） |
