# LAS 功能迁移审计

> 基线：`0f3cfcb`（"LAS 全功能批次"）起，Binggo 一次性吸收 LAS（LotteryAutoScript）
> 的多账号/代理、DS-8/9/10、OCR、抄热评、@与话题、乱序与随机延迟、15 渠道通知、
> 中奖深检、关注分区、清理与 Line 等能力；本文档跟踪这些能力的迁移状态与剩余 gap。
> 当前数据层为 schema v4；回归状态以仓库 CI 为准，不在文档中硬编码测试数量。

## 迁移矩阵

| LAS 能力 | 8/10 基线状态 | 当前实现 | 判定 |
| --- | --- | --- | --- |
| TxT 手动清单 | 无 | DS-8（规范化 ID + fingerprint 增量）+ Data Sources typed 编辑 | ✅ 增强迁移 |
| TAGs 话题源 | 无 | DS-9（最新页 fingerprint，内容变化才补抓历史）+ Data Sources typed 编辑 | ✅ 增强迁移 |
| APIs 外部源 | 无 | DS-10（URL hash key、ETag/Last-Modified、file://、单源降级、全失败显式报错）+ 脱敏增删 UI | ✅ 增强迁移 |
| 评论验证码 OCR | 无 | comment_dynamic OCR 重试 | ✅ 已适配 |
| 抄热评 | 基础随机评论 | `participate_text_mode=random_comment` 为唯一文案来源开关；copy_chat 仅提供 exclude_author/blockwords 等过滤配置 | ✅ 已接线（单控制面） |
| @好友 | 无 | 真实 ctrl 结构化 @；Web 常用表单要求 `uid:昵称`，避免保存后静默失效 | ✅ 已适配 |
| 带话题 | 无 | repost 内容带 topic | ✅ 已适配 |
| 目标乱序 | 无 | 三连 shuffle_targets | ✅ 已适配 |
| 随机动作间隔 | 固定 1.5s | action_interval_sec 范围随机 | ✅ 已适配 |
| 随机动态 | 无 | 未迁移 | ⚪ 产品决策（需验证当前 B 站环境有效性） |
| 15 渠道通知 | 无 | 15 渠道 + 业务码验证 + 飞书官方签名；Web 凭据 fail-closed 加载与脱敏 | ✅ 增强迁移 |
| 中奖深检 | 很弱 | @/回复/私信 + 关键词 + 送达确认后才 mark read；空关键词列表可显式禁用匹配 | ✅ 增强迁移 |
| 多账号 | 单账号 | 账号池 + 显式“添加账号”扫码入口 + 切换 + 账号级代理 + env 覆盖；切号后刷新账号作用域视图 | ⚠️ 管理完成，逐账号自动编排未完成 |
| 账号级代理 | 无 | accounts/{uid}.json + BINGGO_PROXY 优先；Settings 提供当前账号脱敏查看、覆盖与清除 | ✅ 已适配 |
| 关注分区 | 无 | 参与后移入分区（follow 成功才执行），默认关闭；cleanup 自动沿用启用的自定义分区 | ✅ 已适配 |
| clear 动态/取关 | 仅 dead link | dry-run 默认 + 归属台账 + exact created id；Web 明确拆分“动态删除”和“分区取关”副作用并提供预演 | ✅ 安全强化迁移 |
| Line 多线路 | 无 | Line 类（valid_line 会话内记忆） | ⚠️ 基础设施完成，长期 registry 未完成 |
| AI 评论 | 无 | 未发现对应实现 | ⚪ 产品决策 |
| 关注达上限降级 | 无 | 未发现 only_followed 等价状态 | ⚪ 产品决策 |
| per-account 行为配置 / WAIT / NOTE | 无 | proxy 已账号级化；participate_enhance/notify 仍为全局 | ⚠️ 未完整迁移 |

## 已关闭项（不是 bug）

- **EventEmitter → JobRunner + SQLite + SSE**：适应 Web 产品的合理替代。
- **动作顺序调整**（评论→关注→点赞→转发 → 点赞→关注→收藏→转发→评论）：新业务模型，
  含幂等探测与结构化 participation result。
- **DS-8/9/10 每轮全量扫描 → fingerprint/ETag/checkpoint**：更适合长期 Web 服务。
- **关注分区默认关闭**：local-first 产品减少账号副作用，合理选择。
- **随机动态未迁移**：不能因 LAS 有就照搬，需单独验证现实价值。
- **Docker/青龙/pkg/事件总线**：运行形态，不追求语义等价。

## 已完成的语义接线与产品化修复

1. ~~**`participate.dry_run` 贯穿到底层**~~（2026-08 已整体移除参与预演，见下方「已移除功能」）：HTTP dry_run=true 曾在中层被写死
   `dry_run=False, persist=True`（安全契约与真实行为相反）。现 `_execute_participate` /
   `_participate_dynamic_payload` 全程透传 dry_run；单活动页提供独立“预演”入口与
   `status=dry_run` 结果态。预演允许只读获取当前点赞/关注/转发等状态，以决定哪些步骤
   “将执行/已满足”，但不发送点赞、关注、收藏、转发、评论或预约等参与写操作，不写入
   participation 台账，也不把活动标记为“已参加”。
2. **随机评论改为单控制面**：`participate_text_mode` 是用户可见、唯一的文案来源开关。
   选择 `random_comment` 就尝试评论区随机文案；`copy_chat.enabled` 仅保留旧配置兼容，
   不再作为隐藏的第二个 gate。`exclude_author` / `blockwords` 继续作为随机评论过滤配置。
3. **`mark_dm_read` 返回值语义**：该函数失败返回 False（不抛异常），draw_check 检查
   返回值，`acknowledged` 不再误报；只有通知确认送达后才 mark read。
4. **exact ownership**：`repost_dynamic` 记录 API 返回的 `created_dynamic_id`
   （`ActionResult.extra` → actions_json），cleanup 优先精确匹配 feed 转发自身 id，
   旧记录（无 created id）兼容按源动态 id 匹配。
5. **前端配置写入 fail-closed**：Enhance / Notify GET 失败时禁止保存并提示重新加载；
   不再把读取失败伪装成 `{}`，避免一次保存清空真实通知凭据。常用表单基于最后一次
   成功加载的配置深合并，保留前端尚不认识的新字段。
6. **账号上下文刷新**：切换、删除、退出账号后同步刷新账号、summary、activities、
   triple targets 等按 uid 隔离的数据；已登录用户有显式“添加账号”扫码入口。
7. **cleanup UI 与真实副作用对齐**：动态删除和关注分区批量取关分别说明；max_days
   只约束动态删除；自定义关注分区自动联动；“先执行预演”会真实启动 dry-run。
8. **中奖关键词空列表语义**：`None` 才使用 DEFAULT_KEYWORDS，显式 `[]` 表示禁用
   关键词检测，和 Web 文本框清空后的用户意图一致。
9. **正式 Settings / Data Sources 信息架构**：参与文案、LLM、参与增强、通知和账号级
   Proxy 归入 Settings；DS-8/9/10 归入 Data Sources；中奖深检、cleanup、运行日志仍是
   Overview 操作工具，不再用一个 Extra Panel 容器混淆“设置”和“执行”。
10. **DS-10 凭据边界**：Web 只按 source hash ID 增删，GET 仅返回脱敏 URL；认证信息与
    query value 不回显。Web 新增 `file://` 源仅允许位于 `BINGGO_HOME` 内，避免把数据源
    编辑器扩展成任意本地文件读取接口；手工配置文件仍保留高级兼容能力。
11. **账号级 Proxy 控制面**：Settings 显式展示 `BINGGO_PROXY → account → proxy.json →
    direct` 的实际继承来源；保存凭据不回显原文，支持独立清除 account override，且任务
    运行中拒绝修改网络上下文。

## 剩余 gap / roadmap

### P1（产品契约，需决策后实施）
- **多账号编排**：当前已完成 Job 创建时的服务端 `account_uid` 绑定与执行前身份 fail-closed；仍是
  multi-account **management**（账号池+切换+添加），非 LAS 的
  multi-account **orchestration**（无人值守逐账号自动执行）。是否提供“自动逐账号
  轮转”需产品拍板；若做，建议以 `AccountContext`（uid/cookie/proxy/参与配置/通知
  身份/限速状态）为执行单元，Job 绑定 `account_uid` 而非进程当前身份。
- **AI 评论 / only_followed 降级 / 随机动态**：评估在当前 B 站环境是否仍有现实价值。

### P2（架构演进）
- **Line → client-level route registry**：当前 `get_user_followers` 每次新建 `Line`，
  valid_line 不跨调用保留。建议 `BilibiliClient` 持有长期 registry
  （user_info/follow/recommendation/dynamic_detail），而不是调用现场临时构造。
- **per-account 行为配置 / 通知身份上下文**：Proxy 已完成账号级化，但参与增强配置与
  通知仍是全局配置。若后续做自动多账号编排，应让参与策略、通知 NOTE/标题和限速状态
  绑定 `AccountContext`，并在通知中明确中奖账号 UID/备注。

## 已移除功能

### 参与预演（`participate` 的 `dry_run`）—— 2026-08 移除

参与的五个动作是固定的，预演只能复述"将点赞、将关注、将收藏、将转发、将评论"，
提供不了任何决策信息；而它要求 `dry_run` 在 HTTP → `run_action` →
`_execute_participate` → `participate_activity` → `_persist_result` 四层正确透传，
任何一层写死即静默失效——本文档上一节记录的正是这类事故（中层写死
`dry_run=False, persist=True`，安全契约与真实行为完全相反）。

移除范围：`participation.py` / `lottery_actions.py` 的 `dry_run` 形参与分支、
`ParticipationOutcome` 的 `"dry_run"` 态、`web/actions.py` 的透传、
`_ParticipateParams.dry_run`、`scripts/participate.py`、前端"预演"按钮与
预演结果面板。生产代码净 -104 行。

**清理预演保留**：`clear_follows` 的 `dry_run` 默认 True，守的是删动态 + 批量取关
这类真·破坏性操作，且回答的是"会删几条、会取关几人"这种每次都不同、无法预知的数字。
PR-5 恰好证明了它的价值——旧代码预演说 120 人、真实只取关 70 人，
正是靠这个对照面才发现分页收缩缺陷。
