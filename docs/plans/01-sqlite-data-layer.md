# 方向一：数据层方案 — 拍板记录与设计想法

> 状态：**已落地**；实现规范见 [01-sqlite-data-layer-impl.md](./01-sqlite-data-layer-impl.md)  
> 关联：[全栈路线图 §1](../fullstack-roadmap.md)  
> 更新：2026-07-18

本文记录两件事：

1. **拍板结论**（产品/工程边界，已定）  
2. **此前设计想法**（背景与取舍，供实现时对照）

---

## 0. 总前提（已对齐）

| 前提 | 含义 |
|------|------|
| 无真实线上老用户 | **不做**安装包用户的产品级自动升级兼容 |
| 旧策略可删除 | 正式路径以 SQLite 为准，**不保留** JSON 作为长期读写入口 |
| 物料可手动处理 | 通过**开发用导入脚本**保留当前开发机全部数据 |
| 切换必须稳 | 切换后：**项目状态与功能行为不变**；由实现者负责手动切换与回归 |

---

## 1. 拍板结论一览

| 编号 | 议题 | 结论 | 说明 |
|------|------|------|------|
| **A** | 第一期进库范围 | **A2 + A3** | 业务核心 + 监控名单 + 源快照/缓存等一并进库（见 §2） |
| **B** | 与旧 JSON 的关系 | **B1 直接切换** | 不留正式双轨；由实现者**手动切换**，并保证功能稳定 |
| **C** | 统计 counts | **C1 查询时聚合** | 概览/统计用 SQL `COUNT`，不物化汇总表 |
| **D** | 嵌套字段 | **D1 JSON 列** | 奖品、条件等复杂结构进 JSON 字段 |
| **E** | 访问层 | **SQLModel** | 见 §3 说明 |
| **F** | 任务表 | **F1 预留 `jobs`** | 下一步做方向三；建库时预留 schema |
| **G** | 开发机数据 | **G1 导入脚本** | 升级后状态与功能不变；现有数据全部保留 |

---

## 2. 拍板 A 展开：进库范围（A2 + A3）

### 2.1 必须进库（业务核心 + 监控）

| 原文件/概念 | 进库后 |
|-------------|--------|
| `data/output/activities_latest.json` | `activities` 表 |
| `data/users/<uid>/participations.json`（及 legacy） | `participations` 表 |
| `data/users/<uid>/participation_actions.json`（及 legacy） | `participation_actions` 表 |
| `data/state.json` | `source_checkpoints` / `watch_meta` / `pipeline_meta`（或等价拆表） |
| `config/watch_users.json` | `watch_users` 表 |

### 2.2 一并进库（A3：快照与缓存）

| 原文件/概念 | 进库意图 |
|-------------|----------|
| `data/output/ds{1..6}_latest.json` | 各数据源检查结果快照 |
| `data/output/watch_latest.json` | 监控同步快照 |
| `data/cache/forward_parse_cache.json` | 转发解析缓存 |
| `data/cache/forward_classify_cache.json` | 转发分类缓存 |
| `data/cache/account_profile.json` | 账号资料缓存 |
| `data/users/<uid>/message_watch.json` | 消息未读监视 |
| `data/users/<uid>/draw_reminder.json` | 开奖提醒快照（若仍使用） |
| `data/users/<uid>/settings.json` / `config/participate_settings.json` | 参与文案与模式等用户设置（拍板④：进库） |

### 2.3 明确不进库（仍用文件）

| 路径 | 原因 |
|------|------|
| `config/cookies.txt` | 会话密钥，文件/后续方向八治理更合适 |
| `config/llm.env` | API Key，同上 |
| `config/sources.yaml` | 运维向配置 |
| `data/logs/binggo.log` | 滚动日志，保持文件 |
| `data/login_qrcode.png` | 临时图片 |

种子文件（`activities_seed.json` / `state_seed.json` 等）仍可作为**首次空库灌数**的只读源；正式运行态以 DB 为准。

---

## 3. 拍板 E：为何选 SQLModel

用户意向：希望一层技术尽量覆盖「轻量 sqlite3」与「SQLAlchemy ORM」的能力。

**说明（实现时注意）：**

- **SQLModel** = 在 **SQLAlchemy** 引擎/会话之上，用接近 Pydantic 的模型定义表。  
- 它**不是**再发明一套数据库，底层仍是 SQLAlchemy + SQLite。  
- 相对手写 `sqlite3`：模型、关系、与 FastAPI 入参/出参更统一。  
- 相对「只用 SQLAlchemy Core/ORM」：API 层模型可以少写一套重复定义。

**结论：采用 SQLModel（依赖 SQLAlchemy）作为方向一访问层。**  
迁移工具可用 Alembic，或与 SQLModel 配套的版本化迁移策略（实现阶段再定一种，保持单一）。

---

## 4. 拍板 B + G：切换策略（无产品升级器，但要行为不变）

### 4.1 正式路径

- 运行时**只读写 SQLite**（`{DATA_DIR}/binggo.db`，路径仍走 `app_paths.user_home()`）。  
- JSON 活动库 / state / 参与等**不再作为正式 Store 后端**。  
- 旧 Store 实现删除或缩成「仅被导入脚本使用」的只读解析（若需要），**Web/流水线不走 JSON 写**。

### 4.2 开发机数据保留（G1）

提供开发脚本，例如：

```text
python scripts/import_json_to_db.py
```

要求：

- 导入当前 `USER_HOME` 下**已有**活动、参与、动作日志、state、watch、A3 所列缓存/快照等。  
- 导入后：控制台可见数据、筛选统计、参与状态、数据源检查点、监控名单等与导入前**一致**。  
- 可重复执行：**幂等 upsert**（拍板① 乙）；非空库再导须确认或 `--force`，防止误用旧备份覆盖。  
- **第一次导入不得漏数**（硬性验收）：脚本须覆盖 §2.1 / §2.2 / settings 全部进库项；导入结束输出清单与条数核对；缺文件/缺表项则失败退出，不得静默跳过。

### 4.3 手动切换顺序（实现者执行，B1）

推荐顺序（保证稳定）：

1. 落地 schema（含预留 `jobs`）+ Store 新实现（可先并存于分支）。  
2. 用 G1 脚本导入开发机全量数据。  
3. 跑自动化测试 + 手测关键路径（见 §7）。  
4. 切断旧 JSON 写路径并删除无用代码。  
5. 确认无回归后再合并。

**验收红线（拍板要求）：**

> 升级（切换）之后，整个项目的**状态和功能不能改变**——同一份物料下，用户可感知行为与切换前一致。

---

## 5. 拍板 C / D / F（实现约束）

### C1 — 统计

- `user_status_counts`、`counts.active/ended`、`draw_tag_counts` 等：**查询时聚合**。  
- 不再依赖「写 JSON 时塞一份 counts」作为唯一真相（可读兼容层若需要可临时拼出相同结构给前端）。

### D1 — JSON 列

- 活动主表：核心筛选列（如 `dynamic_id`、`lottery_type`、`activity_status`、`lottery_time`、`draw_tag`…）做真正列 + 索引。  
- `prizes` / `conditions` / 其它庞杂字段：JSON 列存储。  
- API/前端仍可得到与现结构等价的 dict（Store 门面负责组装）。

### F1 — 预留 jobs（拍板⑤：瘦字段）

- 建库即包含 `jobs` 表，**仅瘦字段**，方向三再扩展列。  
- 建议列（实现时可微调命名，语义保持）：  
  `id`, `action`, `state`, `progress_step`, `progress_total`, `message`, `log_summary`, `created_at`, `started_at`, `finished_at`  
- 方向一**不实现**完整任务调度语义；方向三再接入 `JobRunner`。

---

## 6. 此前设计想法（背景，供对照）

以下为拍板前的思路摘要；与上节冲突处以**拍板为准**。

### 6.1 为何做方向一

- **并发**：活动整文件读写在三连/状态刷新下易冲突。  
- **查询**：筛选与统计随数据变大变慢。  
- **演进**：方向三任务表、后续检索都需要稳定存储。

### 6.2 原建议的分期（已被拍板 A 加宽）

原想法曾建议 Phase 1 只迁活动/参与/state，A3 缓存后置。  
**现拍板为 A2+A3**，故第一期范围更大：实现时按模块分 PR/提交仍建议分批（先核心表与导入，再缓存表），但**验收以「A3 也在库内」为准**。

### 6.3 库位置与连接

- 文件：`{DATA_DIR}/binggo.db`。  
- 单进程多线程：短事务；**禁止**在持有写事务时打 B 站网络。  
- 模式：先网络/计算，再短事务落库。

### 6.4 Store 门面

- 尽量保持 `activity_store` / `participation_store` / `state_store` 等对上层的函数语义，内部换 SQLModel。  
- 目的：降低 `web/actions.py`、流水线改动面，利于「功能不变」。

### 6.5 原「老用户迁移」想法 — 已废弃

曾讨论：安装包用户平滑升级、长期双写、自动迁移器。  
**按总前提废弃**；仅保留开发用 G1 导入脚本。

### 6.6 与路线图其它方向

| 方向 | 关系 |
|------|------|
| 2 实时推送 | 不阻塞方向一；活动写稳后更适合接 SSE |
| 3 任务抽象 | **下一步**；本方向预留 `jobs` |
| 4 API 契约 | Store 换 DB 后，响应形状尽量不变，减少前端改动 |
| 8 配置安全 | Cookie / llm.env 继续文件 |
| 10 MCP | 读同一 DB/同一 Store，不另搞数据源 |

---

## 7. 切换后建议回归范围（功能不变）

实现完成并导入数据后，至少验证：

- [ ] 概览统计数字与导入前一致（允许实现为实时 COUNT，数值一致即可）  
- [ ] 活动列表筛选 / 搜索 / 分页正常  
- [ ] 单条参与、三连参与：状态与动作日志正确  
- [ ] 一键更新 / 单源更新：检查点推进与「无新专栏跳过」行为不变  
- [ ] 监控用户：名单、同步、状态展示正常  
- [ ] 登录态下 per-uid 参与数据隔离仍正确  
- [ ] LLM 转发抽取仍命中缓存（若导入了 parse/classify cache）  
- [ ] 账号区资料缓存展示正常  
- [ ] Windows 下并行写活动不再依赖整文件 replace（可用现有并行测试加强）

---

## 8. 实现细节拍板进度

### 8.1 已定

| 编号 | 议题 | 结论 |
|------|------|------|
| **②** | 导入后旧 JSON | **留作备份，程序不再读**；路径与运行态数据**分清**（见下） |
| **④** | 用户 settings | **进库**（与 A3 一并） |
| **⑤** | `jobs` 预留 | **瘦字段**（见 §5） |

**② 路径约定（避免混乱）：**

| 角色 | 路径 | 程序是否读写 |
|------|------|----------------|
| 运行态数据库 | `{DATA_DIR}/binggo.db` | ✅ 唯一正式读写 |
| 运行态密钥/配置文件 | `config/cookies.txt`、`llm.env`、`sources.yaml` 等 | ✅ 仍按现逻辑 |
| 运行态日志 | `data/logs/...` | ✅ 日志写入 |
| JSON 备份（导入后） | `{DATA_DIR}/backup/json_pre_sqlite/` 下按原相对路径归档（如 `output/activities_latest.json`、`state.json`、`users/<uid>/...`） | ❌ 运行时不读不写 |
| 导入前原 JSON 位置 | 导入成功并归档后，原位置不再作为 Store 数据源 | ❌ |

导入脚本责任：读当前正式 JSON → 写入 DB → **移动/复制到 `backup/json_pre_sqlite/`**（实现时选定 copy 或 move；推荐 **copy 成功校验后再 move**，失败可回滚）。  
`config/` 下非密钥的 `watch_users.json` 等进库后同样归档到备份树对应位置；`cookies.txt` / `llm.env` **不归档进「废数据」**，继续留在 `config/` 使用。

### 8.2 拍板进度（①、③）

| 编号 | 议题 | 状态 | 结论 |
|------|------|------|------|
| **①** | 导入脚本 | ✅ 已定 | **乙：幂等 upsert**；非空库再导须确认或 `--force` |
| **③** | 表结构版本 | ✅ 已定 | **`schema_version` 启动迁移**（不用 Alembic） |

**① 补充硬性要求（用户）：第一次导入不能漏导入——不可接受静默漏数。**

实现约束：

- 导入范围与 §2.1 / §2.2 / settings 清单一一对应；启动时检查源路径是否存在（应存在却缺失 → **失败退出**并打印缺项）。  
- 结束后打印各类导入条数（活动、参与、动作、检查点、watch、各 cache 等），便于人工核对。  
- 可选：与导入前 JSON 计数交叉校验，不一致则失败。  
- upsert 仅用于「可再跑」；**首次成功标准仍是全量、零遗漏**。

**③ 含义（已定）：** 库内记录当前结构版本号；程序启动时若代码要求的版本更高，则执行对应 SQL 升级（如加列），再更新版本号。不引入 Alembic。

### 8.3 其它实现细节（默认可由实现者定，若要插手再说）

| 项 | 默认倾向 | 是否必须你拍板 |
|----|----------|----------------|
| A3 缓存表主键 / 与现失效逻辑对齐 | 与现模块语义一致 | 否（实现时对照代码） |
| 备份用 copy+校验再 move vs 只 copy | copy+校验再 move | 否（② 已要求分清路径） |
| Store 门面函数名尽量不变 | 保持 | 否 |

---

## 9. 状态

| 项 | 状态 |
|----|------|
| 拍板 A–G | ✅ 已定 |
| 实现细节 ②④⑤ | ✅ 已定 |
| 实现细节 ① | ✅ upsert + 首次全量零遗漏 |
| 实现细节 ③ | ✅ `schema_version` |
| 落地实现规范 | ✅ [01-sqlite-data-layer-impl.md](./01-sqlite-data-layer-impl.md) |
| 编码与切换 | ⏳ 未开始 |
| 方向三接入 jobs | ⏳ 下一步路线 |

讨论记录：

| 日期 | 内容 |
|------|------|
| 2026-07-18 | 确认前提：无老用户兼容；A2+A3、B1 手动稳切、C1、D1、SQLModel、F1、G1 全量导入且行为不变 |
| 2026-07-18 | ② 备份且路径分流；④ settings 进库；⑤ jobs 瘦字段；①③ 待解释后再拍 |
| 2026-07-18 | ③ 定为 schema_version；① 仍待理解后拍板 |
| 2026-07-18 | ① 定为乙 upsert（再导须确认/--force）；首次导入必须全量零遗漏 |
| 2026-07-18 | 落地实现规范成文：01-sqlite-data-layer-impl.md |
