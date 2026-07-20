# 方向四：API 层 — 落地实现规范

> 状态：**已落地（P1–P4）** — 统一错误体 + 契约头 + schemas + 前端双读；验收以 §14 手测 + pytest 为准  
> 拍板依据：[04-api-contract.md](./04-api-contract.md)（**已全部按建议拍板**）  
> 依赖：方向一 Store/DB；方向三 Job 状态机与 `/api/jobs*` 字段；方向二 SSE `/api/events`（本方向**不改**帧格式）  
> 路线图：[fullstack-roadmap.md](../fullstack-roadmap.md) §4  
> 更新：2026-07-19

本文是编码前的最终规范：约束、契约代、错误体系、路由分级、Pydantic schema、各端点请求/响应形状、前端双读、OpenAPI、测试与分期交付。  
**目标红线：** 控制台可感知行为不倒退；旧客户端仍能从顶层 `detail` 读到错误文案；新客户端可用稳定 `error.code`；OpenAPI 对 Stable 路径可用。

---

## 0. 约束摘要（不可违背）

| ID | 约束 |
|----|------|
| A0 | URL **不**搬迁到 `/api/v1`；路径保持现网（A2） |
| A1 | 契约代 **`API_CONTRACT_VERSION = 1`**；JSON API 响应必须带头 `X-Api-Contract: 1`（边角④） |
| A2 | 错误体 **B2**：`error.code` / `error.message` / `error.detail`；过渡期**双写**顶层 `detail = error.message`（I2） |
| A3 | 成功响应 **不加**全局 `{data}` 壳（C1） |
| A4 | 校验失败对外 **HTTP 400** + `VALIDATION_ERROR`，**不**把 422 留给前端（边角①） |
| A5 | **不改** Job 状态机、单槽 409、调度 B1、SSE 事件名与 data 形状（G1） |
| A6 | **不做** Idempotency-Key（F1）；**不做** `GET /api/jobs/{id}` 历史列表（边角③） |
| A7 | 密钥/Cookie/完整 API Key **不得**出现在 JSON 响应、错误 detail、OpenAPI 示例 |
| A8 | 内部未捕获异常：`message` 走友好句（`user_messages` / 现有友好化逻辑）；堆栈只写日志（边角⑤） |
| A9 | `app.py` 路由内**禁止**再直接 `raise HTTPException(detail="中文")`；统一走 `AppError` / helper |
| A10 | 前端 `fetchJSON` 必须双读；启动任务处的 toast 分支优先认 `error.code`（I2） |
| A11 | 业务语义文案（toast 给人看的中文）可微调，但 **code 与 HTTP 映射表冻结**（§3） |
| A12 | 静态资源与 SSE 流式响应：契约头策略见 §2.3（SSE/文件可豁免或可选） |

---

## 1. 拍板对照（实现时勿走样）

| 拍板 | 结论 | 实现落点 |
|------|------|----------|
| A | A2 路径不变 + 契约代 | §2；中间件加头；OpenAPI info |
| B | B2 结构化错误 | §3；`web/api_errors.py` |
| C | C1 无全局壳 | §5 各端点成功体 |
| D | D2 分级 | §4 Stable / Streaming / Internal |
| E | E2 请求+关键模型 | §6 `web/schemas/` |
| F | F1 无幂等键 | 不实现 |
| G | G1 冻结 Job/SSE | §5.4 / §5.5；不改 runner/sse 协议 |
| H | H2 action/错误码清单 | §3 + §7；`ALLOWED_JOB_ACTIONS` 同源 |
| I | I2 双读 | §9 `app.js` |
| J | J1 方法收敛 | §5.7 权威动词表 |
| ① | 422→400 | §3.4 |
| ② | `{ok,job}` | §5.4 |
| ③ | 无历史 API | 不新增 |
| ④ | `X-Api-Contract` | §2 |
| ⑤ | 友好错误 | §3.5 |

---

## 2. 契约代与响应头

### 2.1 常量

```python
# web/api_contract.py（新建，或放在 api_errors.py 顶部）
API_CONTRACT_VERSION = 1
API_CONTRACT_HEADER = "X-Api-Contract"
```

OpenAPI：

```python
app = FastAPI(
    title="Binggo 本地控制台 API",
    version="4.0.2",  # 应用版本，可保持现有
    description="契约代见 X-Api-Contract / API_CONTRACT_VERSION；当前=1",
)
# 建议在 openapi_schema 或 FastAPI 初始化后注入 extension：
# info["x-api-contract"] = 1
```

### 2.2 中间件（推荐）

注册 **HTTP 中间件**（或自定义 `APIRoute`）：

| 响应类型 | 是否强制加 `X-Api-Contract: 1` |
|----------|--------------------------------|
| `application/json` 的 `/api/*` | **必须** |
| `text/event-stream`（`/api/events`） | **建议加**（头在响应开始即可；不改 data 帧） |
| `image/png`、`text/css`、`application/javascript`、StaticFiles | **可不加**（Internal） |

破变更（未来）：递增 `API_CONTRACT_VERSION`，并在本文件与拍板讨论记录说明不兼容点。  
**契约代 1 内允许：** 新增可选字段、新增错误码、新增端点。  
**契约代 1 内禁止：** 删除/改名 Stable 字段、改错误码语义、改 HTTP 大类映射（除非同步升代）。

### 2.3 与 FastAPI 默认错误头

所有经 `AppError` / 统一 handler 发出的 JSON 错误响应同样带 `X-Api-Contract`。

---

## 3. 错误体系（权威）

### 3.1 响应 JSON 形状（固定）

失败时（HTTP ≥ 400）**唯一** JSON 形状：

```json
{
  "error": {
    "code": "AUTH_REQUIRED",
    "message": "请先扫码登录后再执行此操作",
    "detail": null
  },
  "detail": "请先扫码登录后再执行此操作"
}
```

| 字段 | 类型 | 规则 |
|------|------|------|
| `error.code` | string | **稳定枚举**，见 §3.2；只增不改义 |
| `error.message` | string | 给人看的中文；可进 toast；**不要**塞堆栈 |
| `error.detail` | object \| array \| null | 机器可读补充；默认 `null`；校验错误见 §3.4 |
| `detail` | string | **兼容字段** = `error.message`（I2）；旧 `fetchJSON` 可读 |

**禁止：**

- 成功响应里带 `error` 对象（除非将来另有约定，v1 不做）  
- `error.message` 为空字符串（至少给通用「操作失败，请稍后重试」）  
- 把 FastAPI 默认 `{"detail":[{loc,msg,type},...]}` 原样返回给客户端（须经 handler 改写）

### 3.2 错误码表（冻结语义）

| code | HTTP | 何时使用 | 典型 message（可微调文案，勿改 code） |
|------|------|----------|--------------------------------------|
| `VALIDATION_ERROR` | 400 | 参数非法、Pydantic 失败、缺字段、动态 ID/源 ID/MID 无效、未提供可保存设置 | 「活动 ID 无效」等 |
| `UNSUPPORTED_ACTION` | 400 | Job `action` 不在白名单 | 「暂不支持该操作」 |
| `AUTH_REQUIRED` | 401 | 未登录却访问需登录接口 | 「请先扫码登录后再…」 |
| `LLM_NOT_READY` | 401 | 已登录但 LLM 未配置或未通过连接测试（**保持 401**，与现网一致） | 「请先保存 LLM 配置并通过连接测试后再执行此操作」 |
| `NOT_FOUND` | 404 | 监控用户不在列表、二维码文件不存在 | 「用户不在监控列表中」/「二维码尚未生成」 |
| `JOB_BUSY` | 409 | `try_start` 返回 `None` | 「已有任务正在运行」 |
| `JOB_NOT_CANCELLABLE` | 409 | `cancel()` 失败 | 「当前没有可取消的任务」 |
| `AUTO_ALREADY_RUNNING` | 409 | 调度已在运行 | 「调度器已在运行」 |
| `INTERNAL` | 500 | OSError 保存失败、未预期异常 | 「保存 … 失败」或友好通用句 |

**映射硬规则（编码时对照）：**

| 现网场景 | code |
|----------|------|
| `request.action not in ALLOWED_JOB_ACTIONS` | `UNSUPPORTED_ACTION` |
| 未登录 + 业务 Job / settings / watch / LLM test | `AUTH_REQUIRED` |
| `not is_llm_ready()` 挡 refresh/participate | `LLM_NOT_READY`（**不要**再标成 `AUTH_REQUIRED`） |
| `try_start is None` | `JOB_BUSY` |
| `not runner.cancel()` | `JOB_NOT_CANCELLABLE` |
| auto start `RuntimeError("调度器已在运行")` | `AUTO_ALREADY_RUNNING` |
| watch delete 未找到 | `NOT_FOUND` |
| qrcode 文件不存在 | `NOT_FOUND` |
| ValueError 参数类 | `VALIDATION_ERROR` |
| OSError 写文件/配置 | `INTERNAL` |

### 3.3 `AppError` 与抛出方式

新建 `web/api_errors.py`：

```python
class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    LLM_NOT_READY = "LLM_NOT_READY"
    NOT_FOUND = "NOT_FOUND"
    JOB_BUSY = "JOB_BUSY"
    JOB_NOT_CANCELLABLE = "JOB_NOT_CANCELLABLE"
    AUTO_ALREADY_RUNNING = "AUTO_ALREADY_RUNNING"
    INTERNAL = "INTERNAL"

class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        *,
        status_code: int | None = None,
        detail: Any = None,
    ): ...
```

HTTP 默认映射表写死在模块内（与 §3.2 一致）；允许构造时覆盖 `status_code`（一般不需要）。

路由层用法：

```python
raise AppError(ErrorCode.AUTH_REQUIRED, "请先扫码登录后再执行此操作")
raise AppError(ErrorCode.JOB_BUSY, "已有任务正在运行")
```

辅助函数（推荐，减少重复）：

```python
def require_login(account: dict) -> None: ...
def require_llm_ready() -> None: ...
```

### 3.4 Exception handlers（必须注册）

在 `create_app` / `app.py` 模块级注册：

| 异常 | 行为 |
|------|------|
| `AppError` | → §3.1 JSON；状态码来自 AppError |
| `RequestValidationError` | → 400 + `VALIDATION_ERROR`；`error.detail` = 规范化后的字段错误列表（见下）；`error.message` = 「请求参数无效」或首条中文 |
| `HTTPException` | **兼容期**：若仍有遗留，转换为 §3.1（`code` 按 status 粗映射：401→AUTH_REQUIRED，409→JOB_BUSY 或 INTERNAL 需谨慎；**目标是清零路由内 HTTPException**） |
| `Exception` | → 500 + `INTERNAL`；打日志；`message` 友好化 |

**校验 `error.detail` 建议形状：**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数无效",
    "detail": [
      {"loc": ["body", "mid"], "msg": "MID 无效", "type": "value_error"}
    ]
  },
  "detail": "请求参数无效"
}
```

从 FastAPI `RequestValidationError.errors()` 映射即可；`loc` 保持 list。

### 3.5 友好化与日志

- 对 `INTERNAL`：优先复用 `web/user_messages.py`（或现有 `friendly_error`）生成 `message`。  
- `logger.exception` 记录原始异常。  
- **禁止**把 traceback 字符串放进 `error.message` / 顶层 `detail`。

### 3.6 错误体构建函数（单一出口）

```python
def build_error_payload(code: str, message: str, detail: Any = None) -> dict:
    return {
        "error": {"code": code, "message": message, "detail": detail},
        "detail": message,
    }
```

所有 handler 只调用此函数，避免漏双写。

---

## 4. 路由分级（D2）

### 4.1 Stable（正式契约）

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/account` | 账号摘要 |
| GET | `/api/account/extras` | 扩展信息（未读等） |
| POST | `/api/account/ack-at-unread` | 确认 @ 未读 |
| POST | `/api/logout` | 退出登录 |
| GET | `/api/login/qrcode` | 二维码 PNG（成功非 JSON；错误为 JSON） |
| GET | `/api/summary` | 概览统计 |
| GET | `/api/activities` | 活动分页列表 |
| GET | `/api/activities/triple-targets` | 三连预览 |
| POST | `/api/jobs` | 启动任务 |
| POST | `/api/jobs/cancel` | 取消任务 |
| GET | `/api/jobs/current` | 当前/最近任务快照 |
| GET | `/api/auto/status` | 调度状态 |
| POST | `/api/auto/start` | 启动调度 |
| POST | `/api/auto/stop` | 停止调度 |
| GET | `/api/settings` | 设置聚合 |
| GET | `/api/settings/llm` | LLM 公开设置 |
| POST | `/api/settings/llm` | 保存 LLM（权威动词） |
| POST | `/api/settings/llm/test` | 测试 LLM |
| PUT | `/api/settings/participate-text` | 保存参与文案/模式（权威动词） |
| GET | `/api/watch-users` | 监控名单 |
| POST | `/api/watch-users` | 添加监控 |
| DELETE | `/api/watch-users/{mid}` | 删除监控 |

OpenAPI：这些路径加 tag **`stable`**。

### 4.2 Streaming

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/events` | SSE；协议见方向二 impl；本方向仅登记 + 可选契约头 |

OpenAPI tag：`streaming`。响应模型可标 `description` 指向事件目录，**不必**用 Pydantic 描述每一帧。

### 4.3 Internal

| Method | Path |
|--------|------|
| GET | `/app.js`、`/styles.css` |
| mount | `/` StaticFiles |

OpenAPI：可不列入，或 tag `internal`。

### 4.4 Alias / Deprecated（J1）

以 **现网 `app.js` 实际调用**为准：

| Path | 权威 | Alias（保留实现，OpenAPI 标 deprecated） |
|------|------|------------------------------------------|
| `/api/settings/llm` | **POST** | PUT（与 POST 同 handler） |
| `/api/settings/participate-text` | **PUT** | POST（同 handler） |
| `/api/settings/participate-text-mode` | 前端**未使用** | 可保留一版薄封装转调 participate-text，或 OpenAPI deprecated；**不强制删除**以免外部脚本依赖 |

文档与 OpenAPI 示例只展示权威动词。

---

## 5. 各端点契约细节

下列「成功体」字段名为契约；类型以 schema 为准。  
标注 **(frozen)** 的字段来自方向二/三，本方向只建模、不改语义。

### 5.1 Account

#### `GET /api/account`

成功：账号 profile dict（沿用 `get_account_profile()` 现字段）。  
核心字段（响应模型须声明，其余可用 `extra=allow` 或显式可选）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `logged_in` | bool | |
| `uid` / `uname` / `face` 等 | 按现网 | 未登录时按现逻辑给默认 |

错误：一般 200；若服务层抛未登录以外的错误 → 按 §3 映射。

#### `GET /api/account/extras`

成功：extras dict（未读、提醒等）。  
未登录：`AUTH_REQUIRED` 401（保持现网）。

#### `POST /api/account/ack-at-unread`

请求：

```json
{ "current": 0 }
```

`current`：`int >= 0`。  
成功：沿用现返回（通常含 ok / 更新后状态）。  
未登录：`AUTH_REQUIRED`。

#### `POST /api/logout`

成功：`{"ok": true}`  
失败写 cookie：`INTERNAL` 500。

#### `GET /api/login/qrcode`

成功：`FileResponse` PNG。  
失败：JSON `NOT_FOUND`「二维码尚未生成」。

---

### 5.2 Summary / Activities

#### `GET /api/summary`

成功（与 `get_summary()` 对齐）：

| 字段 | 类型 |
|------|------|
| `enriched_at` | any |
| `total_count` | int |
| `new_count` | int |
| `last_pipeline_sync` | object |
| `user_status_counts` | object（已结束/已参加/未参加） |
| `counts` | object（active/ended） |
| `sources` | array |

活动 item 内复杂结构：**不必**在 Summary 里展开；本端点无 items。

#### `GET /api/activities`

Query（全部可选，与现 `Query` 一致）：

| 参数 | 说明 |
|------|------|
| `status` | 参与状态筛选 |
| `type` | → 内部 `lottery_type` |
| `draw` / `draw_window` / `q` / `sort` / `order` | 同现网 |
| `page` | int ≥ 1，默认 1 |
| `page_size` | 接受但服务端可继续固定 `ACTIVITY_PAGE_SIZE`（行为不变） |

成功：

```json
{
  "total": 0,
  "page": 1,
  "page_size": 20,
  "pages": 1,
  "items": [ "..." ],
  "triple_targets": { "count": 0, "items": [], "...": "..." }
}
```

`items[]` 元素：Pydantic 模型声明**稳定展示字段**（`dynamic_id`、`activity_title`、`lottery_type`、`activity_status`、`draw_status`、`can_participate`、`prize`、`repost_count` 等现列表所用）；其余键允许额外字段（`model_config = ConfigDict(extra="allow")`），避免丢掉前端偶用字段。

#### `GET /api/activities/triple-targets`

Query：与列表相同的筛选子集（无 page）。  
成功：`summarize_triple_participate_targets(...)` 现形状（含 `count` / `items` 等）。

---

### 5.3 Watch users

#### `GET /api/watch-users`

成功：在 `get_watch_users_payload` 基础上附加现网字段：

| 字段 | 说明 |
|------|------|
| `count` / `users` / `updated_at` | 名单 |
| `last_synced_at` | |
| `next_window` | 现网已有 |

#### `POST /api/watch-users`

请求：`{"mid": 123}`（已有校验）。  
未登录：`AUTH_REQUIRED`。  
业务 ValueError：`VALIDATION_ERROR` 400。  
其它保存失败：`INTERNAL`。

#### `DELETE /api/watch-users/{mid}`

`mid` 路径参数：正整数。  
未找到：`NOT_FOUND`。  
未登录：`AUTH_REQUIRED`。

---

### 5.4 Jobs（frozen 语义 + 本方向错误码）

#### Job action 枚举（H2，与代码同源）

必须与 `ALLOWED_JOB_ACTIONS` **单一来源**（推荐抽到 `web/job_actions.py` 或 `web/schemas/jobs.py`）：

```text
login
refresh_all
refresh_source
refresh_watch
refresh_status
participate
participate_triple
```

#### `JobStatus` 响应模型（frozen 字段）

与 `JobStatus.to_dict()` 一致：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int \| null | |
| `state` | str | `idle\|running\|success\|error\|cancelled\|interrupted` |
| `action` | str | |
| `label` | str | |
| `source` | str | `ui\|auto\|system` |
| `started_at` / `finished_at` | int \| null | Unix 秒 |
| `message` | str | |
| `log` | str | |
| `result` | object \| null | |
| `progress_step` / `progress_total` | int | |
| `progress_message` | str | |

#### `POST /api/jobs`

请求：

```json
{
  "action": "refresh_all",
  "params": {}
}
```

| 规则 | code |
|------|------|
| action 非法 | `UNSUPPORTED_ACTION` |
| 需登录未登录 | `AUTH_REQUIRED` |
| 需 LLM 未就绪 | `LLM_NOT_READY` |
| refresh_source 源 ID 无效 | `VALIDATION_ERROR` |
| participate dynamic_id 无效 | `VALIDATION_ERROR` |
| 槽位占用 | `JOB_BUSY` |

成功（边角②）：

```json
{
  "ok": true,
  "job": { "...JobStatus..." }
}
```

#### `POST /api/jobs/cancel`

成功：`{"ok": true, "job": {...}}`  
失败：`JOB_NOT_CANCELLABLE` 409。

#### `GET /api/jobs/current`

成功：直接返回 JobStatus 对象（**不是** `{ok, job}`）——保持现网。

---

### 5.5 Auto（frozen 语义）

#### `GET /api/auto/status` / start / stop 成功体

与 `AutoScheduler.get_status()` / `to_dict()` 对齐，响应模型声明主要字段：

`state`, `state_label`, `message`, `started_at`, `stopped_at`, `fatal_error`, `last_tick_at`, `current_phase`, `next_hint`, `next_slot`, `last_click`, `refresh_batch_key`, `triple_slot_key`, `refresh_pipeline`, `job_probe`, `server_now`, `server_now_unix`, `logs`, `schedule`

嵌套对象可用 `dict[str, Any]` 或子模型；`logs` 为 `{ts, level, message}[]`。

#### `POST /api/auto/start`

已运行：`AUTO_ALREADY_RUNNING` 409。  
成功：返回 status 对象（同 get_status）。

#### `POST /api/auto/stop`

成功：返回停止后的 status。  
**语义不变：** 不停业务 Job、不 cancel。

---

### 5.6 Settings

#### `GET /api/settings`

成功字段（现网 `_build_settings_payload`）：

| 字段 |
|------|
| `participate_text`, `default_participate_text` |
| `participate_fallback_text`, `default_participate_fallback_text` |
| `participate_text_mode`, `default_participate_text_mode` |
| `llm`（公开视图，含 hint / ready，**无原始 key**） |
| `setup_complete` |

#### `GET /api/settings/llm`

`{ llm, setup_complete }`

#### `POST /api/settings/llm`（权威）

请求：`LlmSettingsRequest`（api_key / base_url / model_name）。  
未登录：`AUTH_REQUIRED`。  
ValueError：`VALIDATION_ERROR`。  
OSError：`INTERNAL`。  
成功：`{ llm, setup_complete }`。

#### `POST /api/settings/llm/test`

未登录：`AUTH_REQUIRED`。  
连接/配置失败：`VALIDATION_ERROR` 400（保持现网用 400 而非 502）。  
成功：`{ ok, message, llm, setup_complete }`。

#### `PUT /api/settings/participate-text`（权威）

请求：可选三字段（现 `ParticipateTextRequest`）。  
全空：`VALIDATION_ERROR`「未提供可保存的设置」。  
未登录：`AUTH_REQUIRED`。  
成功：只返回实际更新的字段子集（保持现网）。

---

### 5.7 Streaming：`GET /api/events`

- **不改** `format_sse` / 事件名 / data 字段（G1）。  
- 路由可补充 docstring + OpenAPI 描述，链到方向二事件表。  
- 连接建立失败若走 JSON 错误，仍用 §3 错误体（少见）。

---

## 6. 模块与文件布局

```text
web/
  api_contract.py          # 新建：API_CONTRACT_VERSION、头名、可选 openapi 补丁
  api_errors.py            # 新建：ErrorCode、AppError、build_error_payload、register_exception_handlers
  schemas/
    __init__.py
    common.py              # 可共享的小模型
    jobs.py                # JobRequest、JobStatusOut、JobStartOut、ALLOWED_JOB_ACTIONS
    activities.py          # ActivitiesQuery、ActivitiesOut、SummaryOut、TripleTargetsOut
    account.py             # AckAtUnreadRequest、Account 相关 Out（可宽松）
    settings.py            # LlmSettingsRequest、ParticipateTextRequest、SettingsOut…
    auto.py                # AutoStatusOut（关键字段）
    watch.py               # WatchUserRequest、WatchUsersOut
  app.py                   # 变薄：注册 handler/中间件；路由改抛 AppError；response_model=
  static/app.js            # fetchJSON 双读；startJob toast 认 code
tests/
  test_api_errors.py       # 新建：错误体形状、422→400、双写 detail、契约头
  test_web_api.py          # 改编：断言 error.code；保留行为断言
  # 其它既有测试不得无故失败
```

**依赖：** 不新增第三方包；继续 FastAPI + Pydantic v2。

**迁移注意：** 现 `app.py` 内联的 `JobRequest` 等 **移入** `schemas/`，`app.py` 再导入，避免循环依赖（schemas 不导入 runner/scheduler）。

---

## 7. MCP / 多客户端预备（H2）

本方向交付物（文档 + 代码常量即可，**不实现 MCP server**）：

1. **错误码表** = §3.2（可在 `api_errors.py` 用 docstring 或 `ERROR_CATALOG` dict 导出）。  
2. **Job actions** = 与 `ALLOWED_JOB_ACTIONS` 同源的 frozenset / Enum。  
3. OpenAPI `/docs`：Stable 路径可浏览。

方向十应：**HTTP 调用同一 REST**，仅做工具包装，不复制业务。

---

## 8. `app.py` 改造步骤（编码顺序建议）

1. 新建 `api_contract.py` + `api_errors.py`，写单测 `test_api_errors.py`（不依赖完整业务）。  
2. 在 `app` 上 `register_exception_handlers(app)` + 契约头中间件。  
3. 建 `schemas/`，先搬请求模型，路由加 `response_model`（可用模型或 `dict` 过渡，但 Stable 关键须逐步挂上）。  
4. 逐路由替换 `HTTPException` → `AppError`（按 §3.2 表）。  
5. **特别：** LLM 未就绪从「像登录一样的 401 文案」改为明确 `LLM_NOT_READY`（message 可仍用现句）。  
6. 改 `app.js`（§9）。  
7. 改编 `test_web_api.py` + 全量 pytest。  
8. 手测 §14。

---

## 9. 前端改造（I2）

### 9.1 `fetchJSON`（必须）

伪代码：

```javascript
if (!response.ok) {
  const payload = JSON.parse(text);
  const errObj = payload?.error;
  const message =
    (errObj && errObj.message) ||
    (typeof payload?.detail === "string" ? payload.detail : null) ||
    text ||
    response.statusText;
  const error = new Error(message);
  error.code = errObj?.code || "";
  error.httpStatus = response.status;
  error.detail = errObj?.detail ?? null;
  throw error;
}
```

要点：

- 优先 `error.message`，回退字符串 `detail`（兼容）。  
- 若 `detail` 仍是数组（极端旧路径），`message` 回退通用「请求参数无效」，不要 `String([object Object])`。  
- 把 `code` 挂到 Error 上供调用方使用。

### 9.2 启动任务 toast（必须改认 code）

`startJob`（或等价）catch 内：

| 条件 | UI |
|------|-----|
| `error.code === "AUTH_REQUIRED"` 或文案回退含登录 | 请先扫码登录 |
| `error.code === "LLM_NOT_READY"` | 请先测试/配置 LLM（与现两档 toast 对齐） |
| 其它 | `showToast(message, "error")` |

允许短期保留 `message.includes(...)` 作回退，但 **code 分支必须在前**。

### 9.3 其它调用点

本方向**不要求**改完所有中文 includes；优先 Job 启动与 `fetchJSON`。其余可在后续小提交替换。

### 9.4 不做

- 不引入前端类型包 / 构建工具（方向五）。  
- 不改 SSE 订阅逻辑（除非解析错误 JSON 时需容忍新错误体——一般 EventSource 不走 fetchJSON）。

---

## 10. OpenAPI 规范细节

| 项 | 要求 |
|----|------|
| tags | `stable` / `streaming` / `internal`（可选） |
| 每个 Stable 路由 | 有 `summary`；错误响应文档可挂公共 `ErrorBody` 模型 |
| `ErrorBody` | 与 §3.1 一致，列入 components.schemas |
| 示例 | 禁止真实 API Key；llm 示例用 `sk-***` / 空 |
| `/docs` | 本地可打开；作为契约浏览入口 |

可选：自定义 `openapi()` 注入 `x-api-contract: 1` 与错误码表说明段落。

---

## 11. 与既有测试的兼容策略

| 测试 | 策略 |
|------|------|
| `test_web_api.py` | 失败用例改为断言 `resp.json()["error"]["code"]`；同时可断言顶层 `detail` 为 str |
| `test_job_*` / `test_auto_*` | 若走 TestClient 打 API，同步认新错误体；纯 runner 单测不动 |
| 状态码 | 保持 400/401/409/404/500；**新增**：原可能 422 的请求现为 **400** |
| 契约头 | 至少 1 个测试断言 JSON API 响应含 `X-Api-Contract: 1` |

---

## 12. 非目标（再次确认）

- `/api/v1` 前缀、全局 `{data}` 壳、RFC7807  
- Idempotency-Key、Job 历史 API  
- 改 SSE 帧、改 Job 状态机、改调度 B1  
- Vite/TS 前端工程化  
- 实现 MCP server  
- 公网鉴权  

---

## 13. 测试清单（编码必须覆盖）

### 13.1 新建 `tests/test_api_errors.py`

- [ ] `AppError` → 400/401/409 形状含 `error.code` + 顶层 `detail`  
- [ ] 非法 body 触发校验 → **400**（非 422）+ `VALIDATION_ERROR` + `error.detail` 为列表  
- [ ] JSON 成功响应带 `X-Api-Contract: 1`  
- [ ] `POST /api/jobs` unknown action → `UNSUPPORTED_ACTION`  
- [ ] mock 未登录 → `AUTH_REQUIRED`；mock 未 LLM → `LLM_NOT_READY`（可 patch `is_llm_ready`）  
- [ ] `JOB_BUSY`：patch `try_start`→`None`  
- [ ] `JOB_NOT_CANCELLABLE`：patch `cancel`→`False`  

### 13.2 改编 / 回归

- [ ] `test_web_api.py` 全绿  
- [ ] 全量 pytest 绿  
- [ ] 手工：`/docs` 可开  

---

## 14. 手测验收（功能不倒退）

- [ ] 未登录点一键更新 / 三连 → toast 登录（code 或兼容 detail）  
- [ ] 已登录未测 LLM → toast LLM 未就绪（**不应**被误判成「未登录」）  
- [ ] 任务运行中再点其它任务 → 忙  
- [ ] 取消无任务 → 明确提示  
- [ ] 活动列表筛选/分页/三连预览  
- [ ] 保存 LLM（POST）、测试 LLM、参与文案（PUT）  
- [ ] 监控用户增删  
- [ ] Job 进度 SSE 仍正常；调度启停仍正常  
- [ ] 扫码二维码 404/成功仍正常  
- [ ] 浏览器 Network：任一套 JSON API 响应头可见 `X-Api-Contract: 1`  
- [ ] 失败响应 JSON 同时有 `error` 与顶层 `detail`  

---

## 15. 分期交付（建议 PR/提交切分）

| 期 | 内容 | 完成标准 |
|----|------|----------|
| **P1** | `api_errors` + handlers + 契约头中间件 + `test_api_errors` | 任意抛 AppError 形状正确；422→400 |
| **P2** | `schemas/` + 路由 `response_model` + 清零路由内 HTTPException | Stable 路径 OpenAPI 可见模型 |
| **P3** | `app.js` 双读 + Job toast 认 code | 手测登录/LLM 分支正确 |
| **P4** | 改编旧测试 + 全量 pytest + §14 手测 | 可标「已落地」 |

每期保持主分支可运行；禁止「半截错误体」（有的路由新、有的仍纯 `detail` 且无 `error`）——**P1 完成后全局 handler 已统一形状**，路由只需换成 AppError。

---

## 16. 实现检查清单（编码中自检）

- [ ] 无路由 `raise HTTPException(...)`（或仅剩 Static 无关）  
- [ ] `LLM_NOT_READY` 与 `AUTH_REQUIRED` 已分离  
- [ ] `build_error_payload` 单一出口  
- [ ] `ALLOWED_JOB_ACTIONS` 单一来源  
- [ ] settings 权威动词与前端一致  
- [ ] OpenAPI 无真实密钥示例  
- [ ] SSE / Job 字段与方向二/三文档一致  
- [ ] 全量测试通过  

---

## 17. 状态

| 项 | 状态 |
|----|------|
| 拍板 | ✅ 全部按建议 |
| 本实现规范 | ✅ 成文 |
| P1–P4 编码 | ✅ 已落地（全量 pytest 通过） |

手测 §14 请在重启控制台后核对。
