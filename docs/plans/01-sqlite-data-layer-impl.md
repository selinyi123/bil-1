# 方向一：SQLite 数据层 — 落地实现规范

> 状态：**已落地（P1–P5）** — 运行态走 `binggo.db`；开发机用 `scripts/import_json_to_db.py` 全量导入并归档  
> 拍板依据：[01-sqlite-data-layer.md](./01-sqlite-data-layer.md)  
> 路线图：[fullstack-roadmap.md](../fullstack-roadmap.md) §1  
> 更新：2026-07-18

本文是编码说明书：模块划分、表结构、会话与事务、Store 语义保持、导入脚本、schema 版本、切换步骤、测试与验收。  
**目标红线：** 导入现有物料后，控制台可感知状态与功能行为与切换前一致。

---

## 0. 约束摘要（不可违背）

| ID | 约束 |
|----|------|
| C0 | 运行态读写唯一入口：`{DATA_DIR}/binggo.db`；业务 Store **不再**读写活动/参与/state 等 JSON |
| C1 | 不做安装包用户自动升级；开发机用导入脚本保留全量数据 |
| C2 | 首次导入 **零遗漏**：缺应有源文件或条数对不上 → 失败退出，禁止静默跳过 |
| C3 | 再导入：幂等 upsert；非空库须交互确认或 `--force` |
| C4 | 旧 JSON 归档到 `{DATA_DIR}/backup/json_pre_sqlite/`，运行时不读；`cookies.txt` / `llm.env` / `sources.yaml` / 日志仍文件 |
| C5 | 统计 **查询时聚合**（C1）；嵌套用 **JSON 列**（D1）；ORM 用 **SQLModel**；预留瘦 **`jobs`**；settings **进库** |
| C6 | schema 演进用库内 **`schema_version`**，不用 Alembic |
| C7 | **禁止**在持有 DB 写事务期间发起 B 站 / LLM 网络请求 |
| C8 | Store 对外函数名与返回语义尽量不变，降低 `web/`、pipeline 改动面 |

---

## 1. 依赖与目录

### 1.1 依赖（写入 `requirements.txt`）

```
sqlmodel>=0.0.22
```

（会拉取 SQLAlchemy；不引入 Alembic。）

`requirements-dev.txt` 无需为方向一单加项，除非测试另有需要。

### 1.2 新增/调整模块（建议布局）

```
src/
  db/
    __init__.py          # 导出 get_engine / get_session / init_db
    engine.py            # 引擎、连接参数、线程策略
    models.py            # 全部 SQLModel 表定义
    schema.py            # SCHEMA_VERSION、migrate()
    session.py           # Session 上下文管理器
    json_cols.py         # JSON 序列化/反序列化辅助（可选）
  # 改造现有 store（内部换 DB，保留公开 API）：
  activity_store.py
  participation_store.py
  participation_log.py
  state_store.py
  watch_users.py
  user_settings.py
  forward_parse_cache.py
  forward_classify_cache.py
  message_watch.py
  draw_reminder.py
web/
  account_service.py     # account_profile 缓存改 DB
src/sources/common.py    # save_result 写 DB
src/watch_sync.py        # save_watch_result 写 DB
scripts/
  import_json_to_db.py   # G1 导入 + 归档
```

导入脚本可把「只读解析旧 JSON」的辅助函数放在 `src/db/import_json.py`，避免污染运行时 Store。

### 1.3 数据库文件路径

```python
# src/db/engine.py（概念）
from src.app_paths import DATA_DIR
DB_PATH = DATA_DIR / "binggo.db"
# sqlite URL: sqlite:///{DB_PATH.as_posix()}  # Windows 注意绝对路径与四斜杠规则
```

- 开发：`{repo}/data/binggo.db`  
- 安装：`%APPDATA%\Binggo\data\binggo.db`  
- 便携：`{exe目录}/data/binggo.db`  
一律经 `app_paths.DATA_DIR`，禁止写死盘符。

### 1.4 引擎与连接规范

| 项 | 规范 |
|----|------|
| `connect_args` | `{"check_same_thread": False}`（FastAPI/多线程 Job 共用） |
| `pool` | SQLite 默认；可 `StaticPool` 或小 pool；实现时二选一并写注释 |
| `PRAGMA`（连接建立时） | `journal_mode=WAL`；`busy_timeout=5000`（或 3000–8000）；`foreign_keys=ON` |
| 会话 | 短生命周期：`with session_scope() as s:` 用完即 commit/rollback/close |
| 写事务 | 尽量小；先完成网络与内存计算，再 `begin` 写入 |

```python
# session_scope 伪代码规范
@contextmanager
def session_scope():
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

读多写少路径可用同一 `session_scope`；禁止跨请求/跨任务长时间挂着 Session。

---

## 2. Schema 版本（③）

### 2.1 版本表

```sql
CREATE TABLE IF NOT EXISTS schema_meta (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  version INTEGER NOT NULL
);
-- 行：(1, SCHEMA_VERSION)
```

或等价 SQLModel：`SchemaMeta` 单行。

### 2.2 常量

```python
# src/db/schema.py
SCHEMA_VERSION = 1  # 方向一上线版本；后续只增不改历史语义
```

### 2.3 启动迁移流程 `init_db()`

在 `ensure_user_dirs()` **之后**、任何 Store 读写之前调用（见 §9）。

1. 确保 `DATA_DIR` 存在。  
2. 创建 engine；若不存在则创建空文件。  
3. `SQLModel.metadata.create_all`（创建尚不存在的表）。  
4. 读 `schema_meta.version`：  
   - 无行 → 插入 `version=SCHEMA_VERSION`（新库）。  
   - `version < SCHEMA_VERSION` → 按序执行 `migrate_vN_to_vN+1()`，每步成功后更新 version。  
   - `version > SCHEMA_VERSION` → **启动失败**并明确报错（防止旧代码读新库）。  
5. 返回。

方向一仅交付 `SCHEMA_VERSION = 1`（`create_all` 即完整 v1）；`migrate_*` 函数可先留空骨架供方向三加列。

---

## 3. 表结构规范（DDL 语义）

下列为逻辑模型；列名用 snake_case；时间戳一律 **Unix 秒 int**（与现 JSON 一致）；JSON 列存 **UTF-8 JSON 文本**，应用层用 `json.dumps/loads`（`ensure_ascii=False`）。

### 3.1 `schema_meta`

| 列 | 类型 | 约束 |
|----|------|------|
| id | int | PK，恒为 1 |
| version | int | NOT NULL |

### 3.2 `activities`

一行一条活动。筛选列升格；其余进 `payload_json`。

| 列 | 类型 | 约束 / 说明 |
|----|------|-------------|
| dynamic_id | str | **PK** |
| source_url | str \| null | |
| lottery_type | str \| null | 索引 |
| business_id | str \| null | |
| business_type | str \| null | |
| draw_status | str \| null | |
| lottery_time | int \| null | 索引；对应现字段 `lottery_time` |
| activity_status | str \| null | 索引 |
| draw_tag | str \| null | 索引；如「即将开奖」 |
| status_classified | int/bool | 默认 0 |
| skipped | int/bool | 默认 0 |
| platform_participated | int/bool \| null | |
| reserve_reserved | int/bool \| null | |
| repost_count | int \| null | |
| enriched_at | int \| null | |
| status_code | int \| null | |
| skip_reason | str \| null | |
| lottery_detail_url | str \| null | |
| user_status_source | str \| null | |
| payload_json | str/JSON | **D1**：含 `prizes`,`participants`,`conditions`,`winners` 及未升格字段；亦建议冗余完整 item 以便 `to_dict` 无损 |
| updated_at | int | 行更新时间；可用 payload 内时间辅助 |

**索引：** `(lottery_type)`, `(activity_status)`, `(lottery_time)`, `(draw_tag)`, 可选 `(skipped, activity_status)`。

**组装规则 `row_to_activity_dict(row) -> dict`：**

1. 以 `payload_json` 反序列化为 base dict（若为空则 `{}`）。  
2. 用表列覆盖同名键（列优先，保证筛选列与 DB 一致）。  
3. 返回给现有调用方的形状须与现今单条 activity dict **兼容**（前端/流水线不感知存储）。

**写入规则 `activity_dict_to_row(item) -> Activity`：**

1. 抽出升格列。  
2. `payload_json` = 完整 item 的 JSON（或「完整 item 去掉已升格列」——实现二选一，**推荐存完整 item**，读出最不易丢字段）。  
3. Upsert：`dynamic_id` 冲突则更新全部可变列。

### 3.3 `participations`

| 列 | 类型 | 约束 |
|----|------|------|
| uid | str | 与 `dynamic_id` 组成 **复合 PK**；无登录用哨兵 `uid="__legacy__"`（对应现 legacy 根路径语义） |
| dynamic_id | str | |
| user_status | str | `已参加` / `未参加` |
| updated_at | int | |
| source | str \| null | 如 `participate` |

**索引：** `(uid, user_status)`。

**映射：** 现 `get_active_uid()` 有值 → `str(uid)`；无 → `__legacy__`。  
`load_participations()` 仍返回 `dict[dynamic_id, ParticipationRecord]`，**仅当前 active uid（或 legacy）** 作用域，与现行为一致。

### 3.4 `participation_actions`

| 列 | 类型 | 约束 |
|----|------|------|
| id | int | PK 自增 |
| uid | str | 索引；同 sentinel 规则 |
| recorded_at | int | |
| dynamic_id | str | 索引 |
| lottery_type | str | |
| status | str | joined/failed/skipped/dry_run |
| message | str | |
| action_text | str | |
| actions_json | JSON | `list[{action, ok, detail}]` |
| context_snapshot_json | JSON | |

**保留策略：** 与现逻辑一致——每个 `uid` 最多保留最近 **500** 条（追加后删除更旧的）。

### 3.5 `source_checkpoints`（原 `state.sources`）

| 列 | 类型 | 约束 |
|----|------|------|
| source_id | str | PK，如 `DS-1` |
| container_url | str \| null | |
| container_id | str \| null | |
| title | str \| null | |
| cv_id | str \| null | |
| checked_at | int \| null | |

`get_last_container` / `set_last_container` / `get_last_cv_id` 读写本表。

### 3.6 `watch_meta`（原 `state.watch`）

单行或键值表二选一；推荐单行：

| 列 | 类型 | 约束 |
|----|------|------|
| id | int | PK = 1 |
| last_synced_at | int \| null | |

### 3.7 `pipeline_meta`（原 `state.pipeline`）

| 列 | 类型 | 约束 |
|----|------|------|
| id | int | PK = 1 |
| last_action | str \| null | |
| last_persisted_count | int | 默认 0 |
| last_synced_at | int \| null | |

`load_state()` **门面**须仍返回：

```json
{
  "sources": { "DS-n": { ... } },
  "watch": { "last_synced_at": ... },
  "pipeline": { "last_action", "last_persisted_count", "last_synced_at" }
}
```

以便现有调用不改。`save_state(state)`：拆写三表（事务内）。

### 3.8 `watch_users`

| 列 | 类型 | 约束 |
|----|------|------|
| mid | int | PK |
| name | str | |
| updated_at | int | 名单级更新时间可冗余在每行或另表；保持 `get_watch_users_payload` 的 `updated_at`/`count`/`users` |

可选列：`seeded_from` 放 `app_kv` 或本表元数据行。

### 3.9 `user_settings`

| 列 | 类型 | 约束 |
|----|------|------|
| uid | str | PK；全局未登录用 `__global__`（对应现 `config/participate_settings.json`） |
| participate_text | str \| null | |
| participate_fallback_text | str \| null | |
| participate_text_mode | str \| null | `custom` / `random_comment` |
| updated_at | int | |

路径语义：`get_active_uid()` 有值 → `str(uid)`；否则 `__global__`。

### 3.10 `ds_check_snapshots`（原 `ds{n}_latest.json`）

| 列 | 类型 | 约束 |
|----|------|------|
| source_id | str | PK（`DS-1`…`DS-6`） |
| updated | int/bool | |
| container_url | str \| null | |
| container_id | str \| null | |
| title | str \| null | |
| published_at | int \| null | |
| previous_container_url | str \| null | |
| checked_at | int \| null | |
| cv_id | str \| null | |
| activity_links_json | JSON | `list[str]` |
| link_hints_json | JSON | `dict[str, str]` |
| raw_json | JSON | 可选：完整 `to_dict()` 备份防丢字段 |

**注意现行为：** `save_result` 仅在 `updated=True` 时落盘。迁 DB 后保持同一语义：未更新可不写或写标记，**不得改变**「无新专栏不推进文件」所表达的检查点逻辑（检查点在 `source_checkpoints`，由 `commit_source_checkpoint` 负责）。

### 3.11 `watch_sync_snapshots`（原 `watch_latest.json`）

| 列 | 类型 | 约束 |
|----|------|------|
| id | int | PK = 1（只保留最新一份，与现单文件一致） |
| source_id | str | 默认 `WATCH` |
| synced_at | int | |
| window_start | int \| null | |
| window_end | int \| null | |
| checked_at | int \| null | |
| activity_links_json | JSON | |
| link_count | int | |
| users_total | int | |
| users_ok | int | |
| users_failed | int | |
| user_results_json | JSON | |
| raw_json | JSON | 可选完整备份 |

### 3.12 `forward_parse_cache`

| 列 | 类型 | 约束 |
|----|------|------|
| dynamic_id | str | PK |
| content_hash | str | |
| parsed_json | JSON | |
| updated_at | int | |

命中逻辑保持：`content_hash == md5(normalize_ws(text))` 且 parser_version 匹配（版本校验仍在 `forward_parser` 侧）。

### 3.13 `forward_classify_cache`

同构：`dynamic_id` PK + `content_hash` + `parsed_json` + `updated_at`。

### 3.14 `account_profile_cache`

| 列 | 类型 | 约束 |
|----|------|------|
| id | int | PK = 1 |
| uname | str \| null | |
| face | str \| null | |
| mid | int \| null | |
| following | int \| null | |
| dynamic_count | int \| null | |
| updated_at | int | |
| raw_json | JSON | 可选 |

与现磁盘一致：只持久化上述字段子集。

### 3.15 `message_watch`

| 列 | 类型 | 约束 |
|----|------|------|
| uid | int 或 str | PK（与现 `message_watch_path(uid: int)` 对齐，用 int） |
| last_seen_unread_at | int \| null | |
| updated_at | int | |

### 3.16 `draw_reminder_snapshots`

| 列 | 类型 | 约束 |
|----|------|------|
| uid | int | PK |
| drawing_soon_count | int | |
| drawing_soon_json | JSON | |
| at_notify_url | str \| null | |
| updated_at | int | |

即使当前少有调用方，仍按拍板 A3 建表并支持导入。

### 3.17 `jobs`（预留瘦表，方向一不接入调度）

| 列 | 类型 | 约束 |
|----|------|------|
| id | int | PK 自增 |
| action | str | |
| state | str | 如 idle/queued/running/success/error/cancelled（方向三再严格枚举） |
| progress_step | int | 默认 0 |
| progress_total | int | 默认 0 |
| message | str | 默认 `""` |
| log_summary | str | 默认 `""` |
| created_at | int \| null | |
| started_at | int \| null | |
| finished_at | int \| null | |

方向一：表存在即可；`JobRunner` **仍用内存**，不在本方向切换。

### 3.18 可选 `app_kv`

用于 `seeded_from`、导入指纹等杂项：

| 列 | 类型 |
|----|------|
| key | str PK |
| value_json | JSON |

非必须；也可用 `schema_meta` 旁扩展。

---

## 4. Store 改造规范（行为保持）

### 4.1 总则

1. **公开函数签名与返回类型不变**（见拍板文档与下文清单）。  
2. 删除或停用对 `ACTIVITIES_OUTPUT_PATH` 等 JSON 的运行时读写。  
3. 进程内锁：  
   - 活动：可用短事务替代整文件锁；若上层仍调用 `activity_file_lock()`，保留 API 但改为 **可重入的逻辑锁或 no-op 文档化**——**推荐保留 RLock** 包裹「读改写多步」以降低并发语义变化风险，内部再开 session。  
   - `user_data_lock`：参与状态 + 动作日志仍建议同一把锁内完成，与现 `participation.py` 一致；锁内只做 DB 事务。  
4. `load_payload()` 必须继续返回含 `activities`、`counts`、`user_status_counts`、`draw_tag_counts`、`updated_at` 的 dict；其中 counts **现场聚合**（§5）。

### 4.2 `activity_store` 聚合算法（C1）

与现 `_empty_payload` / 统计语义对齐（实现时对照 `activity_store` / `activity_service.get_summary`）：

- `counts.active` / `counts.ended`：按 `activity_status`（或项目现用判定）COUNT。  
- `user_status_counts`：需结合 **当前 uid** 的 `participations`（与现概览一致：未登录/已登录规则照旧）。  
- `draw_tag_counts`：如对 `draw_tag="即将开奖"` COUNT。  
- `updated_at`：`MAX(activities.updated_at)` 或维护的库级时间戳。

**禁止**再写一份仅存在于 JSON 顶层、与明细不一致的 counts 作为唯一真相。

### 4.3 必须保持的公开 API 清单

| 模块 | 函数 |
|------|------|
| activity_store | `activity_file_lock`, `seed_activities_if_empty`, `load_payload`, `load_activities`, `known_activity_ids`, `append_activities`, `replace_all_activities`, `remove_activity_ids`, `update_activity`, `collect_urls_from_ids` |
| participation_store | `load_participations`, `set_participation`, `set_participation_unlocked` |
| participation_log | `serialize_actions`, `append_action_record`, `append_action_record_unlocked`, `participation_succeeded`, `all_core_actions_ok` |
| state_store | `seed_state_if_missing`, `load_state`, `save_state`, `get_last_container`, `get_last_cv_id`, `set_last_container`, `get_watch_last_synced_at`, `set_watch_last_synced_at`, `set_last_pipeline_persisted`, `get_last_pipeline_persisted` |
| watch_users | `seed_from_candidates_if_empty`, `list_watch_users`, `get_watch_users_payload`, `add_watch_user`, `remove_watch_user` |
| user_settings | 全部 get/set/normalize* |
| forward_*_cache | load/get/put/(merge) 现有 API |
| message_watch / draw_reminder | 现有 path/get/save/compute API |
| sources.common | `save_result` 语义；改为写 `ds_check_snapshots` |
| watch_sync | `save_watch_result` → `watch_sync_snapshots` |
| account_service | `_save_account_cache` / 读取改为 DB |

`status_refresh.persist_activity_record` 等继续调用 `activity_store` / 锁；内部改为 DB 事务。

### 4.4 种子（空库）

- `seed_activities_if_empty`：若 `activities` 表无行 → 从 `activity_seed` 解析 JSON 种子写入 DB（不再写 `activities_latest.json`）。  
- `seed_state_if_missing`：若 `source_checkpoints` 无行 → 从 state seed 写入。  
- `watch_users.seed_from_candidates_if_empty`：表空时从 candidates 文件导入（candidates 文件可仍留在 config 作种子源）。  
- `ensure_user_dirs` → `_bootstrap_user_data`：在 `init_db()` 之后调用上述 seed。

**顺序：**

```
ensure_user_dirs()  # mkdir + 复制 example 配置
init_db()           # 新建：在 ensure 内或紧接其后，见 §9
seed_state_if_missing()
seed_activities_if_empty()
```

---

## 5. 导入脚本规范（G1 + ①）

### 5.1 入口

```bash
python scripts/import_json_to_db.py
python scripts/import_json_to_db.py --force
```

- 工作根：`app_paths.user_home()` / `DATA_DIR` / `CONFIG_DIR`。  
- 先 `ensure_user_dirs()` + `init_db()`。

### 5.2 非空库保护

若库中已有任一业务表行数 > 0（`activities` 或 `participations` 等，实现时定义「非空」判定）：

- 无 `--force` 且非交互确认 → **退出码 ≠ 0**。  
- 交互确认文案须写明将 upsert 覆盖风险。

### 5.3 导入清单（必须全覆盖；缺则失败）

「应存在」规则：

| 源路径（相对 USER_HOME） | 目标表 | 缺失时 |
|--------------------------|--------|--------|
| `data/output/activities_latest.json` | activities | **失败**（开发机应有；若确无可用种子则须显式 `--allow-seed-activities` 另议，默认失败） |
| `data/state.json` | checkpoints/meta | **失败** |
| `config/watch_users.json` | watch_users | 若无则尝试 candidates；两者都无 → **失败** |
| `data/users/*/participations.json` 与 legacy `data/participations.json` | participations | 全无则记 0 条但 **须在报告中列出已扫描路径**；若 users 目录存在却读失败 → 失败 |
| 同理 `participation_actions` | participation_actions | 同上 |
| `data/users/*/settings.json` + `config/participate_settings.json` | user_settings | 允许 0，须扫描报告 |
| `data/output/ds1_latest.json` … `ds6_latest.json` | ds_check_snapshots | 每个：文件不存在 → 该源记「跳过(文件不存在)」**不算漏数**；文件存在但 JSON 损坏 → **失败** |
| `data/output/watch_latest.json` | watch_sync_snapshots | 不存在可跳过；损坏失败 |
| `data/cache/forward_parse_cache.json` | forward_parse_cache | 不存在可跳过；损坏失败 |
| `data/cache/forward_classify_cache.json` | forward_classify_cache | 同上 |
| `data/cache/account_profile.json` | account_profile_cache | 同上 |
| `data/users/*/message_watch.json` | message_watch | 扫描 users |
| `data/users/*/draw_reminder.json` | draw_reminder_snapshots | 扫描 users |

**零遗漏定义：**  
- 计划导入的「存在且可读」文件必须全部成功写入；  
- 结束时打印 **计划文件列表 + 每类条数 + 跳过原因**；  
- 任何「存在但未导入」→ 失败。  
对「文件本就不存在」的可选缓存，允许跳过但必须打印，不得假装已导入。

建议实现 **强制校验**：导入前统计 JSON 内条目数，导入后 `SELECT COUNT` 对比（activities / participations per uid / cache entries 等），不一致失败。

### 5.4 Upsert 键

| 表 | 冲突键 |
|----|--------|
| activities | dynamic_id |
| participations | (uid, dynamic_id) |
| participation_actions | 追加为主；再导入时建议按 `(uid, recorded_at, dynamic_id, status)` 去重或先删该 uid 再导——**推荐再导入前对 actions：按 uid 删除再批量插入**（报告写明），避免重复日志 |
| source_checkpoints | source_id |
| watch_users | mid |
| user_settings | uid |
| ds_check_snapshots | source_id |
| watch_sync / account | id=1 覆盖 |
| forward_*_cache | dynamic_id |
| message_watch / draw_reminder | uid |

### 5.5 归档（②）

成功提交 DB 后：

1. 对每个已成功导入的源文件：`copy2` → `{DATA_DIR}/backup/json_pre_sqlite/<相对 data 或 config 的路径>`。  
2. 校验备份文件 size/hash。  
3. 再 `unlink` 原路径（move 语义）。  
4. **永不归档：** `config/cookies.txt`, `config/llm.env`, `config/sources.yaml`, `config/*.example`, 种子 `*_seed.json`（种子可留作空库 bootstrap）, `data/logs/**`, `data/login_qrcode.png`。  
5. `watch_users.json` 进库后归档；`watch_users_candidates.json` **保留**作种子源。

备份目录示例：

```
data/backup/json_pre_sqlite/
  data/output/activities_latest.json
  data/state.json
  data/users/<uid>/participations.json
  config/watch_users.json
  ...
```

（相对路径在备份根下保持可识别结构；实现时统一用「相对 USER_HOME」或「相对 DATA_DIR+CONFIG」一种，并在脚本头注释写死。）

### 5.6 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 2 | 非空库未确认 |
| 3 | 源缺失/损坏/校验失败 |
| 4 | DB 错误 |

---

## 6. 并发与锁（替换文件锁后的策略）

| 场景 | 策略 |
|------|------|
| 多线程 `persist_activity_record` | 每条短事务 upsert；WAL + busy_timeout；保留 `activity_file_lock` 可选串行化整段 RMW |
| `replace_all_activities` | 单事务：清空或差异更新 + 插入（注意性能；可 delete all + bulk insert） |
| 参与 + 动作日志 | `user_data_lock` + 单事务写两表 |
| DS 并行 check | 各写不同 `source_id` 快照行；`set_last_container` 行级 upsert，靠 SQLite 锁 |
| forward cache | 单行 upsert；可用细粒度锁或依赖 SQLite |

测试：保留/改写 `tests/test_status_refresh.py` 中并行写用例，断言无异常且行数正确。

---

## 7. 前端 / API 契约

- **不改** REST 路径与 JSON 字段名（方向四另做）。  
- `get_summary` / 活动列表继续消费 Store 门面。  
- 若某处直接 `Path.read_text` 读 `activities_latest.json`，实现阶段 **grep 清零**，全部改 Store。

---

## 8. 删除与禁止事项（切换完成后）

运行时禁止：

- 写 `activities_latest.json` / `state.json` / `participations.json` / `ds*_latest.json` / 各 cache json（除导入脚本读旧文件）。  
- 长期双写 JSON+DB。

允许保留只读常量路径仅供导入脚本与测试夹具使用，或迁入 `src/db/legacy_paths.py`。

---

## 9. 启动顺序（全进程）

所有入口（`web/app.py`、`run_dashboard.py`、`binggo_launcher.py` 等）统一：

```python
ensure_user_dirs()   # 目录 + example 配置复制
init_db()            # schema_version + create_all
# 然后 seed_*（空库灌种子）
```

`init_db` 必须幂等、可重复调用。

---

## 10. 实现分期（仍一次验收 A2+A3）

编码可分提交，**功能验收以全部完成且导入成功为准**：

| 阶段 | 交付 |
|------|------|
| P1 | `src/db/*`、依赖、`init_db`、models v1（含 jobs） |
| P2 | activity + participation + actions + state 门面切 DB |
| P3 | watch_users、settings、message_watch、draw_reminder、account cache、forward caches、ds/watch 快照 |
| P4 | `import_json_to_db.py`（全量、校验、归档） |
| P5 | 删除运行时 JSON 写；修测试；全量回归 |
| P6 | 开发机执行导入 + 手测清单 |

---

## 11. 测试规范

### 11.1 必做自动化

| 测试 | 断言 |
|------|------|
| DB init | 重复 `init_db` 不报错；version=1 |
| activity CRUD | append/update/replace/load_payload counts 一致 |
| participation 事务 | set_participation + append_action 同 uid |
| state | set_last_container / pipeline / watch 往返 |
| 并行 persist | 多线程写不同/相同 dynamic_id 不崩溃 |
| 导入 dry | 用 tmp_path 构造最小 JSON 集，导入后 COUNT 匹配；缺文件失败 |
| 导入非空 | 无 force 拒绝 |
| 种子 | 空库 seed_activities / seed_state 仍可用 |

### 11.2 手测清单（切换后）

同拍板文档 §7，并增加：

- [x] 导入报告条数与导入前抽查一致  
- [x] `data/backup/json_pre_sqlite/` 存在且原路径业务 JSON 已移走  
- [x] `cookies.txt` / `llm.env` 仍在原处可用  
- [x] 重启进程后数据仍在（证明不在内存）

---

## 12. 手动切换操作手册（实现者）

1. 提交前：开发分支完成 P1–P5，CI/本地 pytest 通过。  
2. **备份整份** `{USER_HOME}`（手动压缩一份，双保险）。  
3. 跑 `python scripts/import_json_to_db.py`，确认退出码 0 与报告。  
4. 启动控制台，按 §11.2 手测。  
5. 问题则：停服，恢复 USER_HOME 备份，修脚本/代码后重来（upsert --force）。  
6. 通过后合并；README/路线图状态更新为方向一完成。

---

## 13. 风险与缓解

| 风险 | 缓解 |
|------|------|
| payload_json 丢字段 | 存完整 activity dict；单测 round-trip |
| uid sentinel 不一致 | 文档写死 `__legacy__` / `__global__`；集中函数 `resolve_participation_uid()` |
| WAL 文件残留 | 正常；备份时带上 `binggo.db*` |
| 导入漏可选 cache | 报告区分「必需失败」与「可选跳过」 |
| `replace_all_activities` 过慢 | bulk insert；必要时临时关索引（一般千级不需要） |
| Windows 路径 URL | 单测覆盖绝对路径建引擎 |

---

## 14. 非目标（本方向不做）

- JobRunner 持久化到 `jobs`（方向三）  
- SSE/WebSocket（方向二）  
- Alembic、Postgres、多用户 SaaS  
- Cookie/LLM 密钥入库  
- 产品级自动迁移弹窗  
- 对话式 Agent

---

## 15. 验收定义（Definition of Done）

- [x] `requirements.txt` 含 sqlmodel；`init_db` 全入口调用  
- [x] 全部 §3 表存在；`jobs` 瘦表存在但未接管调度  
- [x] 所有 §4.3 Store API 走 DB；grep 无运行时写业务 JSON  
- [x] 导入脚本满足零遗漏 + upsert + 归档路径分流  
- [x] 自动化测试通过；手测清单勾完（`scripts/handtest_data_layer.py` + pytest）  
- [x] 拍板文档与路线图状态更新  

---

## 16. 文档关系

| 文档 | 职责 |
|------|------|
| [01-sqlite-data-layer.md](./01-sqlite-data-layer.md) | 拍板与产品边界 |
| **本文** | 编码级规范与表/流程细节 |
| [fullstack-roadmap.md](../fullstack-roadmap.md) | 十方向总览 |

实现中若发现本文与代码历史行为冲突：**以「保持用户可感知行为」为最高优先级**，修正本文并记入讨论记录，而不是静默改变产品行为。
