# LAS 功能迁移审计

> 基线：`0f3cfcb`（"LAS 全功能批次"）起，Binggo 一次性吸收 LAS（LotteryAutoScript）
> 的多账号/代理、DS-8/9/10、OCR、抄热评、@与话题、乱序与随机延迟、15 渠道通知、
> 中奖深检、关注分区、清理与 Line 等能力；本文档跟踪这些能力的迁移状态与剩余 gap。
> 当前数据层为 schema v3；回归状态以仓库 CI 为准，不在文档中硬编码测试数量。

## 迁移矩阵

| LAS 能力 | 8/10 基线状态 | 当前实现 | 判定 |
| --- | --- | --- | --- |
| TxT 手动清单 | 无 | DS-8（规范化 ID + fingerprint 增量） | ✅ 增强迁移 |
| TAGs 话题源 | 无 | DS-9（最新页 fingerprint，内容变化才补抓历史） | ✅ 增强迁移 |
| APIs 外部源 | 无 | DS-10（URL hash key、ETag/Last-Modified、file://、单源降级、全失败显式报错） | ✅ 增强迁移 |
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
| 账号级代理 | 无 | accounts/{uid}.json + BINGGO_PROXY 优先；暂未提供 Web 编辑入口 | ⚠️ 后端已适配，前端管理待补 |
| 关注分区 | 无 | 参与后移入分区（follow 成功才执行），默认关闭；cleanup 自动沿用启用的自定义分区 | ✅ 已适配 |
| clear 动态/取关 | 仅 dead link | dry-run 默认 + 归属台账 + exact created id；Web 明确拆分“动态删除”和“分区取关”副作用并提供预演 | ✅ 安全强化迁移 |
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

## 已完成的语义接线修复

1. **`participate.dry_run` 贯穿到底层**：HTTP dry_run=true 曾在中层被写死
   `dry_run=False, persist=True`（安全契约与真实行为相反）。现 `_execute_participate` /
   `_participate_dynamic_payload` 全程透传 dry_run；是否允许状态刷新等读侧行为以当前
   Web 契约为准，不再把 dry_run 偷换为真实参与。
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

## 剩余 gap / roadmap

### P1（产品契约，需决策后实施）
- **多账号编排**：当前是 multi-account **management**（账号池+切换+添加），非 LAS 的
  multi-account **orchestration**（无人值守逐账号自动执行）。是否提供“自动逐账号
  轮转”需产品拍板；若做，建议以 `AccountContext`（uid/cookie/proxy/参与配置/通知
  身份/限速状态）为执行单元，Job 绑定 `account_uid` 而非进程当前身份。
- **AI 评论 / only_followed 降级 / 随机动态**：评估在当前 B 站环境是否仍有现实价值。

### P2（前端产品化）
- **DS-8/9/10 编辑入口**：当前 Web 能看到并刷新三个源，但清单/话题/API URL 仍需编辑
  本地配置文件；建议新增 typed source-settings API 后再做 UI，不让浏览器直接写任意路径。
- **账号级代理 UI**：后端已有 per-account proxy metadata，Web 暂无安全的读取/覆盖入口；
  需要先定义凭据脱敏、继承优先级和连接测试语义。
- **单活动 dry-run UI**：后端已支持，但当前参与结果组件会把 `status=dry_run` 误渲染为
  “参与未完成”；必须连同结构化 result view 一起接入，不能只补按钮。
- **Settings / Tools 信息架构**：新增设置仍集中在 Overview Extra Panels，后续应拆出正式
  Settings / Tools 导航，避免继续堆叠。

### P2（架构演进）
- **Line → client-level route registry**：当前 `get_user_followers` 每次新建 `Line`，
  valid_line 不跨调用保留。建议 `BilibiliClient` 持有长期 registry
  （user_info/follow/recommendation/dynamic_detail），而不是调用现场临时构造。
- **per-account 行为配置 / 通知身份上下文**：多账号编排落地后，参与增强配置与
  通知标题（当前“Binggo：账号可能中奖了”）应带账号身份（uid/NOTE）。
