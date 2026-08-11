# LAS 功能迁移审计

> 基线：`0f3cfcb`（"LAS 全功能批次"）起，Binggo 一次性吸收 LAS（LotteryAutoScript）
> 的多账号/代理、DS-8/9/10、OCR、抄热评、@与话题、乱序与随机延迟、15 渠道通知、
> 中奖深检、关注分区、清理与 Line 等能力；本文档跟踪这些能力的迁移状态与剩余 gap。
> 生成于当前 HEAD（schema v3、610+ 测试通过）。

## 迁移矩阵

| LAS 能力 | 8/10 基线状态 | 当前实现 | 判定 |
| --- | --- | --- | --- |
| TxT 手动清单 | 无 | DS-8（规范化 ID + fingerprint 增量） | ✅ 增强迁移 |
| TAGs 话题源 | 无 | DS-9（最新页 fingerprint，内容变化才补抓历史） | ✅ 增强迁移 |
| APIs 外部源 | 无 | DS-10（URL hash key、ETag/Last-Modified、file://、单源降级、全失败显式报错） | ✅ 增强迁移 |
| 评论验证码 OCR | 无 | comment_dynamic OCR 重试 | ✅ 已适配 |
| 抄热评 | 基础随机评论 | copy_chat（enabled 权威开关 + exclude_author + blockwords） | ✅ 已接线（enabled 统一） |
| @好友 | 无 | 真实 ctrl 结构化 @ | ✅ 已适配 |
| 带话题 | 无 | repost 内容带 topic | ✅ 已适配 |
| 目标乱序 | 无 | 三连 shuffle_targets | ✅ 已适配 |
| 随机动作间隔 | 固定 1.5s | action_interval_sec 范围随机 | ✅ 已适配 |
| 随机动态 | 无 | 未迁移 | ⚪ 产品决策（需验证当前 B 站环境有效性） |
| 15 渠道通知 | 无 | 15 渠道 + 业务码验证 + 飞书官方签名 | ✅ 增强迁移 |
| 中奖深检 | 很弱 | @/回复/私信 + 关键词 + 送达确认后才 mark read | ✅ 增强迁移 |
| 多账号 | 单账号 | 账号池 + 切换 + 账号级代理 + env 覆盖 | ⚠️ 账号管理完成，逐账号自动编排未完成 |
| 账号级代理 | 无 | accounts/{uid}.json + BINGGO_PROXY 优先 | ✅ 已适配 |
| 关注分区 | 无 | 参与后移入分区（follow 成功才执行），默认关闭 | ✅ 已适配 |
| clear 动态/取关 | 仅 dead link | dry-run 默认 + 归属台账 + exact created id | ✅ 安全强化迁移 |
| Line 多线路 | 无 | Line 类（valid_line 会话内记忆） | ⚠️ 基础设施完成，长期 registry 未完成 |
| AI 评论 | 无 | 未发现对应实现 | ⚪ 产品决策 |
| 关注达上限降级 | 无 | 未发现 only_followed 等价状态 | ⚪ 产品决策 |
| per-account 行为配置 / WAIT / NOTE | 无 | 仅账号级 proxy；participate_enhance/notify 全局 | ⚠️ 未完整迁移 |

## 已关闭项（不是 bug）

- **EventEmitter → JobRunner + SQLite + SSE**：适应 Web 产品的合理替代。
- **动作顺序调整**（评论→关注→点赞→转发 → 点赞→关注→收藏→转发→评论）：新业务模型，
  含幂等探测与结构化 participation result。
- **DS-8/9/10 每轮全量扫描 → fingerprint/ETag/checkpoint**：更适合长期 Web 服务。
- **关注分区默认关闭**：local-first 产品减少账号副作用，合理选择。
- **随机动态未迁移**：不能因 LAS 有就照搬，需单独验证现实价值。
- **Docker/青龙/pkg/事件总线**：运行形态，不追求语义等价。

## 已完成的语义接线修复（本轮）

1. **`participate.dry_run` 贯穿到底层**：HTTP dry_run=true 曾在中层被写死
   `dry_run=False, persist=True`（安全契约与真实行为相反）。现 `_execute_participate` /
   `_participate_dynamic_payload` 全程透传 dry_run，预演模式不产生真实副作用、
   不持久化、不改活动库状态；`_require_participate_success` 认可 `dry_run` 终态。
2. **`copy_chat.enabled` 成为"抄热评"权威开关**：此前只读 `exclude_author/blockwords`，
   enabled 形同虚设；现 `random_comment` 模式 + enabled=True 才请求评论区抄热评，
   关闭时回退固定文案。
3. **`mark_dm_read` 返回值语义**：该函数失败返回 False（不抛异常），draw_check 现
   检查返回值，`acknowledged` 不再误报。
4. **exact ownership**：`repost_dynamic` 记录 API 返回的 `created_dynamic_id`
   （`ActionResult.extra` → actions_json），cleanup 优先精确匹配 feed 转发自身 id，
   旧记录（无 created id）兼容按源动态 id 匹配。

## 剩余 gap / roadmap

### P1（产品契约，需决策后实施）
- **多账号编排**：当前是 multi-account **management**（账号池+切换），非 LAS 的
  multi-account **orchestration**（无人值守逐账号自动执行）。是否提供"自动逐账号
  轮转"需产品拍板；若做，建议以 `AccountContext`（uid/cookie/proxy/参与配置/通知
  身份/限速状态）为执行单元，Job 绑定 `account_uid` 而非进程当前身份。
- **AI 评论 / only_followed 降级 / 随机动态**：评估在当前 B 站环境是否仍有现实价值。

### P2（架构演进）
- **Line → client-level route registry**：当前 `get_user_followers` 每次新建 `Line`，
  valid_line 不跨调用保留。建议 `BilibiliClient` 持有长期 registry
  （user_info/follow/recommendation/dynamic_detail），而不是调用现场临时构造。
- **per-account 行为配置 / 通知身份上下文**：多账号编排落地后，参与增强配置与
  通知标题（当前"Binggo：账号可能中奖了"）应带账号身份（uid/NOTE）。

### 观察项
- `judge_keywords(patterns or DEFAULT_KEYWORDS)`：显式传 `[]` 仍启用默认关键词，
  若 UI 支持清空关键词需明确"空列表=禁用"语义。
