# 方向八：配置与安全 — 落地实现规范

> 状态：**已落地（P1–P3）** — 编码对照本文；验收以 §16 为准  

> 拍板依据：[08-config-security.md](./08-config-security.md)（**已全部按建议拍板**：A1/B2/C1/D1/E1/F1/G1/H1/I1/J1）  
> 依赖：方向一（密钥不进库）、方向四（统一错误体）、方向五（前端模块）、方向七（`log_redact` / diagnostics）  
> 路线图：[fullstack-roadmap.md](../fullstack-roadmap.md) §8  
> 更新：2026-07-20

本文是编码前的最终规范：约束、敏感清单、文件权限、LLM/Cookie 校验、启动自检、loopback、文档/UI、CI 防泄漏、分期与验收。  
**目标红线：**  
1. 敏感路径/键名有**单一清单**，脱敏 / 诊断 / 自检 / 防泄漏检查同源；  
2. LLM 读写经模型校验；Cookie 写入做关键字段存在性校验；  
3. 密钥文件写入后**尽力**收紧权限（失败不阻断业务）；  
4. 启动软自检 + 概览展示数据目录 / runtime；  
5. **不**做静态加密；**不**改登录 / LLM 保存测试 / 参与文案的用户可感知语义。

---

## 0. 约束摘要（不可违背）

| ID | 约束 |
|----|------|
| **S0** | **不改业务语义**：扫码登录、退出、LLM 保存/测试/hint、参与文案、Job/SSE 行为均不动 |
| **S1** | 密钥落盘 = **明文文件**（拍板 **A1**）；**禁止** DPAPI / keyring / 把密钥写入 SQLite |
| **S2** | 路径钉死（边角 **①**）：`{CONFIG_DIR}/cookies.txt`、`{CONFIG_DIR}/llm.env`；**不改名** |
| **S3** | 配置校验 = 加载/写入时模型校验（**B2**）；**禁止**上全面 `pydantic-settings` 大一统（B3） |
| **S4** | 文件权限 = **尽力**收紧（**C1**）；失败只警告，**不得**导致登录/保存失败 |
| **S5** | 启动自检 = **软**（**D1**）；**禁止**因自检失败拒绝启动控制台 |
| **S6** | 路径策略保持三模式（**E1**）；只对齐文档与 UI 展示 |
| **S7** | 敏感清单单一模块（**F1**）；`log_redact` / `sanitize_params` / diagnostics / 自检 **引用同一来源** |
| **S8** | HTTP 意图钉死 loopback（**G1**）；**禁止**在 README/打包说明推荐 `0.0.0.0` |
| **S9** | 脱敏以方向七为准（**H1**）；本方向只做清单对齐与缺口补齐，不重写脱敏引擎 |
| **S10** | 环境变量旁路保留（边角 **②**）：`BILI_COOKIE`、`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_NAME` |
| **S11** | `api_key_hint` 掩码规则保持（边角 **③**）；保存空 Key 仍表示「保留旧 Key」 |
| **S12** | 契约代不变：设置类 API 错误走方向四统一错误体；**不**新增 ErrorCode 语义除非确有必要（优先 `VALIDATION_ERROR`） |

---

## 1. 拍板对照（实现时勿走样）

| 拍板 | 结论 | 实现落点 |
|------|------|----------|
| A | A1 明文 + 硬化 | §0 S1 / 全文不引入加密 |
| B | B2 读写模型校验 | §5 / §6 |
| C | C1 尽力权限 | §4 |
| D | D1 软自检 + 轻 UI | §7 / §11 |
| E | E1 保持三模式 | §8 / §12 |
| F | F1 单一清单 | §3 |
| G | G1 loopback | §9 |
| H | H1 复用 redact | §3.4 / §10 |
| I | I1 ignore + 轻检查 | §13 |
| J | J1 最小 UI | §11 |
| ① | 路径钉死 | §2 / §3.2 |
| ② | 保留 env 旁路 | §5.5 / §6.3 / §7 |
| ③ | hint 保持 | §5.6 |
| ④ | 卸载保留 APPDATA | §12 |
| ⑤ | pytest 为主 | §13 / §14 |
| ⑥ | 分期 P1→P3 | §15 |

---

## 2. 目标目录与文件（编码后应存在）

```text
src/
  secrets_inventory.py     # 新建：敏感文件/环境变量/键名/诊断排除权威清单
  secure_files.py          # 新建：尽力 chmod/ACL；原子写可选复用
  config_validate.py       # 新建（或并入 llm_settings）：LLM/Cookie 校验模型与纯函数
  config_health.py         # 新建：启动自检，返回结构化 findings
  llm_settings.py          # 改造：读写走校验；写后 harden_permissions
  llm_config.py            # 改造：load 路径兼容坏文件（警告+降级）
  bilibili_login.py        # 改造：save_cookies 校验关键字段 + harden
  bilibili_client.py       # 小改：可选调用 cookie 校验（读侧不阻断）
  account_service.py       # 小改：has_login_cookie 与校验语义对齐（若需）
  log_redact.py            # 小改：SECRET 键名从 inventory 派生或交叉断言
  job_store.py             # 小改：sanitize 键规则与 inventory 对齐
  diagnostics.py           # 小改：显式引用 inventory 排除列表（防御式注释/断言）
  app_paths.py             # 小改：导出 runtime 信息辅助；ensure 后可调自检入口
  dashboard_server.py      # 小改：启动前断言 host 为 loopback

web/
  app.py                   # 小改：settings/runtime 载荷；启动链调用自检
  schemas/settings.py      # 小改：可选加强 Field；或保持薄壳由服务层校验
  schemas/runtime.py       # 新建（可选）：RuntimeInfoOut

web/frontend/
  index.html               # 概览 project-showcase 增加数据目录 / runtime 展示
  src/settings/index.ts    # 或新建 src/runtime/index.ts：填充目录信息
  src/bootstrap.ts         # 绑定加载

tests/
  test_secrets_inventory.py
  test_secure_files.py
  test_config_validate.py
  test_config_health.py
  test_git_secrets_not_tracked.py   # I1
  # 更新既有：test_llm_settings / test_bilibili_login_* / test_app_paths / test_log_redact

docs/
  plans/08-config-security.md       # 状态改为已拍板
  plans/08-config-security-impl.md  # 本文
README.md                           # 数据目录 / 密钥 / loopback 对齐
packaging/windows/README.md         # 同上 + 便携风险 + 卸载保留
```

**禁止：**

- 引入 `keyring` / DPAPI / 加密容器作为 v1 验收项  
- 把 Cookie / API Key 写入 `binggo.db` 或 diagnostics bundle  
- 为「安全」改绑 `0.0.0.0` 或在文档中推荐  
- 大改设置页交互、强制用户重填 LLM Key  
- 自检失败 `sys.exit` / 阻止 `uvicorn.run`

---

## 3. 敏感清单（F1，权威）— `src/secrets_inventory.py`

本模块是**唯一权威来源**。其它模块只 import 常量/辅助函数，禁止再复制一套字符串列表（测试可断言集合相等）。

### 3.1 必须导出的常量与函数

```python
# 文件名（相对 CONFIG_DIR；不含目录）
SECRET_FILENAMES: frozenset[str] = frozenset({
    "cookies.txt",
    "llm.env",
})

# 诊断包 / 任意导出绝对不得读取的路径解析
def secret_file_paths() -> list[Path]:
    """返回 [COOKIE_PATH, LLM_ENV_PATH]，一律经 app_paths。"""

# 环境变量名（完整匹配，大小写敏感按 OS 惯例；清单用规范大写）
SECRET_ENV_VARS: frozenset[str] = frozenset({
    "BILI_COOKIE",
    "LLM_API_KEY",
    # 下列本身不是「密钥」，但是配置旁路；自检「覆盖提示」用
})

CONFIG_OVERRIDE_ENV_VARS: frozenset[str] = frozenset({
    "BILI_COOKIE",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL_NAME",
})

# 字典键：用于 redact（全键名匹配，大小写不敏感）
REDACT_SECRET_KEY_NAMES: frozenset[str] = frozenset({
    "cookie",
    "token",
    "secret",
    "password",
    "authorization",
    "api_key",
    "api-key",
})

# 字典键：用于 job sanitize（子串匹配，保持现网更严行为）
SANITIZE_SECRET_KEY_SUBSTR: frozenset[str] = frozenset({
    "cookie",
    "token",
    "secret",
    "password",
    "authorization",
    "api_key",
    "api-key",
})

def is_redact_secret_key(name: str) -> bool: ...
def is_sanitize_secret_key(name: str) -> bool: ...
```

### 3.2 与现网对齐规则（勿悄悄改严/改松）

| 消费者 | 现行为 | 本方向要求 |
|--------|--------|------------|
| `log_redact._SECRET_KEY_RE` | `^(cookie\|token\|…\|api[_-]?key)$` | 改为由 `REDACT_SECRET_KEY_NAMES` 编译，或运行时调用 `is_redact_secret_key`；**语义保持全键匹配** |
| `job_store._SECRET_KEY_RE` | 子串 search | 保持子串；由 `SANITIZE_SECRET_KEY_SUBSTR` 派生 |
| `diagnostics` | 结构上不读密钥文件 | 增加注释 + 可选断言：`secret_file_paths()` 不在读取列表；**仍禁止**把文件内容拼进 bundle |
| `.gitignore` | 已忽略两文件 | 保持；I1 测试对照 `SECRET_FILENAMES` |

**刻意保留的差异：** redact 全匹配 vs sanitize 子串 —— 写进模块 docstring，禁止「为了统一」把 sanitize 改成全匹配（会放宽 `my_cookie` 类键的丢弃）。

### 3.3 非密钥（明确不要塞进 SECRET_FILENAMES）

| 路径 | 原因 |
|------|------|
| `sources.yaml` | 运维配置，无账号密钥 |
| `watch_users.json` | UID 列表，非登录态 |
| `participate_settings.json` | 遗留路径；运行态文案在 DB |
| `binggo.db` | 诊断包已排除整库；属数据不是「密钥文件清单」主项（可在 diagnostics 文档注明） |
| `data/logs/binggo.log` | 已脱敏；可导出有界行 |

### 3.4 文本脱敏模式

**保留**方向七 `log_redact._PATTERNS`（SESSDATA / bili_jct / Bearer / LLM_API_KEY= / JWT / 长 base64 等）。  
本方向**不**要求把 regex 也搬进 inventory（避免 inventory 变成正则动物园）；但：

- 新增「键名」类规则必须先改 inventory；  
- 若新增 Cookie 相关 cookie 键（如 `buvid3`）——**默认不做**，除非拍板扩展（非本方向验收）。

---

## 4. 文件权限（C1）— `src/secure_files.py`

### 4.1 API

```python
def harden_file_permissions(path: Path) -> bool:
    """尽力将 path 收紧为仅当前用户可读写。
    成功 True；跳过/失败 False（已打 warning 日志）。
    文件不存在 → False，不抛。
    """

def write_text_secret(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """推荐：原子写（tmp + replace）后 harden_file_permissions。
    失败 harden 不抛。
    """
```

### 4.2 平台行为

| 平台 | 行为 |
|------|------|
| **POSIX** | `os.chmod(path, 0o600)`；若已是更严可保持 |
| **Windows** | **尽力**：优先尝试去掉「Everyone/Users 读」类继承（可用 `icacls` 子进程 **或** `ctypes`/win32 ACL）；若实现成本高或测试不稳，**允许 v1 仅文档 + POSIX 实现**，Windows 打 debug/info「已跳过 ACL」——但 **API 必须存在且调用点必须挂上**，以便日后补强 |
| 任意 | 捕获一切异常 → `logger.warning("无法收紧权限 path=%s: %s", path, exc)` → 返回 False |

**硬性：** `harden_file_permissions` **永不**抛到业务层；`save_cookies` / `save_llm_settings` 不因权限失败回滚已写入内容。

### 4.3 必须调用的写点

| 写点 | 文件 | 现状 | 改造 |
|------|------|------|------|
| `bilibili_login.save_cookies` | `cookies.txt` | 已有 tmp+replace | replace 成功后 `harden_file_permissions(COOKIE_PATH)`；可改用 `write_text_secret` |
| `llm_settings._write_values` | `llm.env` | `write_text` 非原子 | **改为原子写** + harden（与 cookie 同级） |
| `account_service.clear_login_cookie` | 删除或写空 | unlink / 写空 | 若残留空文件则 harden；删除则无需 |

### 4.4 不调用的写点

- `sources.yaml` 首次复制、example 复制、日志轮转、DB 写入 —— **不是**密钥文件。

### 4.5 测试

- POSIX（CI Ubuntu）：写入临时文件后 `stat.st_mode & 0o777 == 0o600`（或至少 group/other 无读）。  
- Windows：调用不抛；返回值 True/False 均可接受（勿因 ACL 失败红测）。

---

## 5. LLM 配置校验（B2）

### 5.1 模型定义（推荐放 `src/config_validate.py` 或 `llm_settings.py`）

使用已有依赖 **pydantic v2**（项目已用），**不**新增 `pydantic-settings` 包（除非编码时发现必需——默认不需要）。

```python
class LlmEnvFileModel(BaseModel):
    model_config = ConfigDict(extra="ignore")  # 文件里多出的键忽略，勿 forbid 以免老文件炸

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL_NAME: str = ""
    LLM_TEST_PASSED: str = "false"
    LLM_TEST_FINGERPRINT: str = ""
```

另设**写入意图**模型（API/保存用）：

```python
class LlmSettingsWriteModel(BaseModel):
    api_key: str = ""          # 空 = 保留旧 key（与现网一致）
    base_url: str = ""
    model_name: str            # 保存时必填（与现 save_llm_settings 一致）
```

URL 规则**复用**现 `_resolve_base_url` 语义：

| 输入 | 结果 |
|------|------|
| 空 | 使用 `DEFAULT_LLM_BASE_URL` |
| `http://` / `https://` 且有 netloc | 通过，`rstrip("/")` |
| `file://` / `ftp://` / 无 netloc / 乱串 | `ValueError` → API `VALIDATION_ERROR` |

### 5.2 读写路径改造

| 函数 | 规范 |
|------|------|
| `_parse_env_file` | 解析后 `LlmEnvFileModel.model_validate(dict)`；校验失败 → 记 warning，返回空/安全默认 dict，**不抛穿启动** |
| `get_llm_config` / `load_llm_config` | 坏文件 → `None`（LLM 未就绪），与现「无 key/model → None」一致 |
| `save_llm_settings` | 先走写入模型 + `_resolve_base_url`；**校验通过才写盘**；写后 harden；仍清空 `TEST_PASSED` / fingerprint（现语义） |
| `build_llm_config_from_inputs` | 保持；非法 URL 仍 `ValueError` |
| `mark_llm_test_passed` | 保持「必须与已保存三元组一致」 |

### 5.3 API 层（`web/schemas/settings.py` + `web/app.py`）

- `LlmSettingsRequest` 可继续薄壳（`extra=forbid`）；**权威校验仍在服务层**，避免双源真相。  
- 可选增强：对 `base_url` 做 max_length（如 500）、`model_name` max_length（如 200）——**不得**把空 `api_key` 标成必填。  
- 错误：继续 `AppError(ErrorCode.VALIDATION_ERROR, …)`。

### 5.4 公开响应（不变）

`get_llm_settings_public()` 字段保持：

```text
configured, test_passed, ready, base_url, model_name, api_key_hint
```

**禁止**回传明文 `api_key`。`mask_api_key` 算法不变（边角③）。

### 5.5 环境变量优先级（钉死，边角②）

与现 `llm_config.load_llm_config` 一致：

1. 若 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL_NAME` **三者皆非空** → 用环境变量构造（不读文件）。  
2. 否则读 `llm.env`（经校验模型）。

自检（§7）在检测到任一 `CONFIG_OVERRIDE_ENV_VARS` 非空时提示「配置正被环境变量影响」，**不禁止**。

---

## 6. Cookie 校验（B2 的 Cookie 半边）

### 6.1 校验函数

```python
def validate_cookie_string(cookie_str: str) -> str:
    """返回 strip 后的内容；不合法抛 ValueError（中文消息）。"""
```

**规则（写入时强制）：**

1. strip 后非空（保持现 `save_cookies`）。  
2. **必须**能解析出 `SESSDATA`（大小写不敏感键名，值非空）。  
3. **必须**能解析出 `bili_jct`（非空）——与 CSRF 需求对齐。  
4. **建议**有 `DedeUserID`（非空）；若缺失 → **warning 日志仍允许保存**（兼容历史极简 cookie），或与实现者二选一：**推荐硬性要求 DedeUserID** 与扫码产物一致。  
   - **编码默认（本文钉死）：** `SESSDATA` + `bili_jct` **硬性**；`DedeUserID` **软性**（缺则 warning）。

解析：复用 / 抽取 `bilibili_auth` 现有正则，避免第三套解析。

### 6.2 调用点

| 点 | 行为 |
|----|------|
| `save_cookies` | 校验失败 → `BilibiliLoginError` 或 `ValueError`（与现错误类型风格一致）；成功才写盘 + harden |
| `_load_cookie_string` | **不**因缺字段拒绝加载（避免突然登出）；可选 debug 日志 |
| `has_login_cookie` | 保持「文件非空且含 SESSDATA」；可改为调用同一解析辅助，语义不变 |

### 6.3 `BILI_COOKIE` 旁路

- 读取优先环境变量（现行为）。  
- 自检提示覆盖。  
- **不**对环境变量做写入校验。

---

## 7. 启动自检（D1）— `src/config_health.py`

### 7.1 数据结构

```python
@dataclass(frozen=True)
class HealthFinding:
    code: str          # 稳定机读码，如 "secret_perms_wide"
    severity: str      # "info" | "warning" | "error"（error 仍不阻断启动）
    message: str       # 中文人话
    path: str | None = None

@dataclass(frozen=True)
class HealthReport:
    runtime: str                 # runtime_label()
    user_home: str
    data_dir: str
    config_dir: str
    version: str
    bind_host: str               # 期望 "127.0.0.1"
    findings: list[HealthFinding]

def run_config_health_checks() -> HealthReport: ...
def log_config_health(report: HealthReport | None = None) -> HealthReport: ...
```

### 7.2 检查项（v1 必须实现）

| code | severity | 条件 | message 要点 |
|------|----------|------|----------------|
| `runtime_info` | info | 始终 | 记录 runtime / user_home / data_dir（也可不放 findings，放 report 顶栏） |
| `env_cookie_override` | warning | `BILI_COOKIE` 非空 | 登录态可能来自环境变量而非 cookies.txt |
| `env_llm_override` | warning | `LLM_API_KEY` 等影响加载 | LLM 可能来自环境变量 |
| `secret_file_perms` | warning | POSIX 上密钥文件 other/group 可读 | 权限过宽，已尝试或建议检查 |
| `cookie_missing_fields` | warning | 文件存在但缺 SESSDATA/bili_jct | 建议重新扫码登录 |
| `llm_env_invalid` | warning | 文件存在但模型校验失败 | 请到控制台重新保存 LLM |
| `bind_host_ok` | info | host 为 127.0.0.1 | （可只打日志不进 findings） |

**不做（v1）：** 扫描「是否在 OneDrive 目录」等启发式（误报多）；改为文档提示。

### 7.3 调用时机

| 入口 | 时机 |
|------|------|
| `scripts/run_dashboard.py` | `ensure_user_dirs` + `setup_logging` 之后、`run_dashboard_server` 之前 |
| `web/app.py` 模块加载 | `ensure_user_dirs` + `setup_logging` 之后调用 `log_config_health()`（TestClient 也会触发——须**快速、无网络、幂等**；可用模块级 flag 避免重复刷屏，或 findings 只 log 一次） |
| 打包启动器 | 若走同一 dashboard 入口则自动覆盖 |

**禁止**在自检里：读整个日志文件、连 B 站、写库。

### 7.4 日志格式

使用 `get_logger("config")`，每条 finding 一行；敏感路径只打 path，**不打文件内容**。

---

## 8. 路径策略（E1）— 只对齐，不改算法

### 8.1 保持 `user_home()` 优先级

1. `BINGGO_HOME`  
2. frozen + portable → `bundle_root()`  
3. frozen → `%APPDATA%\Binggo`（或 `~/Binggo`）  
4. 开发 → 仓库根  

### 8.2 `runtime_label()` 注意

现状用导入时 `USER_HOME` 快照。实现时：

- **推荐：** `runtime_label()` 改为基于 **当前** `user_home()` / `is_frozen()` / portable 环境变量计算，避免测试 patch 后标签不准。  
- 若改动面大，至少在 `HealthReport` 里用动态 `user_home()`，标签与路径一致。

### 8.3 文档三处对齐（§12）

说法必须一致：

| 模式 | 数据根 | 密钥位置 |
|------|--------|----------|
| 开发 | 仓库根 | `config/cookies.txt`、`config/llm.env` |
| 安装 | `%APPDATA%\Binggo` | 同上相对路径 |
| 便携 | exe 同目录 | 同上；**勿整夹同步到公开网盘** |
| 覆盖 | `BINGGO_HOME` | `{BINGGO_HOME}/config/...` |

卸载：**安装版卸载不删除** `%APPDATA%\Binggo`（边角④）。

---

## 9. Loopback（G1）— `src/dashboard_server.py`

### 9.1 现状（保持）

```python
DASHBOARD_HOST = "127.0.0.1"
# uvicorn.run(..., host=DASHBOARD_HOST, port=get_dashboard_port())
```

开发端口 `8787`，打包 `8181` —— **不改**。

### 9.2 硬化

```python
def assert_loopback_host(host: str = DASHBOARD_HOST) -> None:
    allowed = {"127.0.0.1", "localhost", "::1"}
    if host not in allowed:
        raise RuntimeError(
            f"拒绝绑定非 loopback 地址: {host!r}（仅允许 {sorted(allowed)}）"
        )
```

- `run_dashboard_server` **开头**调用。  
- 若未来有人改常量，启动直接失败（开发期防呆）。  
- **不**提供环境变量改绑到 `0.0.0.0` 的「官方开关」。

### 9.3 文档

README / packaging README 写明：服务只监听本机；**不要**改成局域网开放。

---

## 10. 与方向七对齐（H1）

| 模块 | 动作 |
|------|------|
| `log_redact.py` | 键名集合改由 inventory 派生；patterns 保留；补测「inventory 键均被 redact」 |
| `diagnostics.py` | 文件头注释列出 `secret_file_paths()`；组装逻辑仍不读这些文件；bundle 可增加一行 `secrets_excluded: cookies.txt,llm.env`（**仅文件名**） |
| `job_store.sanitize_params` | 正则/集合改由 inventory 派生；行为保持丢弃键 |

**回归：** 既有 `test_log_redact` / `test_diagnostics_api` / `test_job_store` 全绿。

---

## 11. API 与前端（J1，最小）

### 11.1 后端载荷

在**不破坏**现有字段前提下扩展。推荐二选一（实现时选 A）：

**方案 A（推荐）：** 扩展 `_build_settings_payload()` / 或新建轻量接口：

```http
GET /api/runtime
```

```json
{
  "ok": true,
  "version": "4.0.2",
  "runtime": "dev",
  "user_home": "...",
  "data_dir": "...",
  "config_dir": "...",
  "bind_host": "127.0.0.1",
  "bind_port": 8787,
  "findings": [ { "code": "...", "severity": "warning", "message": "..." } ]
}
```

- `tags=["stable"]` 或 `internal`：因含本机路径，**推荐 `stable` 但仅本机使用**；不要把 findings 当安全评分。  
- findings **不得**包含密钥内容。

**方案 B：** 把 `runtime` / `data_dir` 塞进现有 `GET /api/settings`。注意前端兼容；字段只增不删。

### 11.2 前端展示位置

概览页 `article.project-showcase` 侧栏（已有 Repository / Author / License）**追加卡片**：

| Label | Value |
|-------|-------|
| Runtime | `dev` / `installed` / `portable` |
| 数据目录 | `data_dir` 文本（可 `title` 满路径；过长 CSS 截断） |

可选：若存在 `severity=warning` 的 findings，在导出诊断包旁显示一行 caption（非模态恐吓）。

**不改：** LLM 表单、登录区、任务坞、导出诊断包主流程。

### 11.3 前端模块

- 新建 `web/frontend/src/runtime/index.ts`：`loadRuntimeInfo()` + 填 DOM。  
- `bootstrap.ts` 启动时调用（失败静默，不影响主功能）。

---

## 12. 文档改造（E1 / ④ / G1）

### 12.1 `README.md` 必须补齐/对齐的段落

1. 数据目录三模式表（开发 / 安装 / 便携 / `BINGGO_HOME`）。  
2. 密钥文件路径与「已 gitignore」说明（可链到现有安全提示）。  
3. 服务地址仅本机 `127.0.0.1`。  
4. 安装版卸载不删 `%APPDATA%\Binggo`。  
5. 便携：密钥与程序同目录，勿同步到公开位置。

### 12.2 `packaging/windows/README.md`

同上精简版 + `BinggoPortable.cmd` / `BINGGO_PORTABLE=1` 提示。

### 12.3 不在本方向做

应用内自动更新文案（方向九）；MCP 安全（方向十）。

---

## 13. Git / CI 防泄漏（I1）

### 13.1 测试（必做）

`tests/test_git_secrets_not_tracked.py`：

```python
def test_secret_filenames_not_tracked():
    # git ls-files -- config/cookies.txt config/llm.env
    # 或 ls-files 全量后断言 SECRET_FILENAMES 无命中
    # 在非 git 环境 skip
```

另测：`.gitignore` 含这些路径（读文件断言）——可选。

### 13.2 CI（推荐与测试合并）

不必单独 job：pytest 已跑该测试即可。若希望显式步骤，可在 `ci.yml` pytest job 加：

```yaml
- name: Ensure secrets not tracked
  run: |
    ! git ls-files --error-unmatch config/cookies.txt 2>nul
    ! git ls-files --error-unmatch config/llm.env 2>nul
```

（Windows runner 语法不同；**优先依赖跨平台 pytest**。）

### 13.3 不引入

强制 pre-commit hook 框架（可另议）；密钥扫描 SaaS。

---

## 14. 测试矩阵（边角⑤）

| 测试文件 | 覆盖 |
|----------|------|
| `test_secrets_inventory.py` | 常量完备；`secret_file_paths` 指向 app_paths；与 redact/sanitize 派生一致 |
| `test_secure_files.py` | POSIX 0o600；不存在路径；异常吞掉 |
| `test_config_validate.py` | Cookie 缺 SESSDATA 失败；LLM URL 非法失败；合法通过 |
| `test_config_health.py` | env 覆盖产生 warning；不抛；无网络 |
| `test_git_secrets_not_tracked.py` | I1 |
| 更新 `test_llm_settings.py` | 保存非法 URL 不落盘；原子写后文件内容正确 |
| 更新 `test_bilibili_login_*` | 缺 bili_jct 拒绝保存；harden 被调用（可 mock） |
| 更新 `test_app_paths.py` | `runtime_label` 与动态 home（若改） |
| 更新 `test_log_redact.py` / diagnostics | 回归 |
| 可选 `test_runtime_api.py` | `GET /api/runtime` 形状 |

**不强制**新 Playwright E2E；若加，只 smoke「概览可见数据目录文案」。

---

## 15. 分期（边角⑥）

| 期 | 内容 | 退出标准 |
|----|------|----------|
| **P1** | `secrets_inventory` + `secure_files` + LLM/Cookie 校验 + 写点 harden + redact/sanitize/diagnostics 对齐 + README/packaging 文档 | 单测绿；手动保存 LLM/登录不回归 |
| **P2** | `config_health` + `GET /api/runtime`（或 settings 扩展）+ 前端展示数据目录/runtime + loopback assert | 启动日志有自检；概览可见目录 |
| **P3** | `test_git_secrets_not_tracked`（+ 可选 CI 步骤）+ 补测缺口 | I1 亮灯 |

允许 P1+P3 同 PR；P2 UI 可同 PR 若改动小。

---

## 16. 验收红线

编码完成后必须满足：

- [ ] 存在 `src/secrets_inventory.py`；redact / sanitize / diagnostics 排除与之同源  
- [ ] `save_cookies`：缺 `SESSDATA` 或 `bili_jct` → 不写盘；成功后调用 harden  
- [ ] `save_llm_settings`：非法 base_url → `VALIDATION_ERROR` 且文件不被写成坏值；成功后原子写 + harden  
- [ ] 启动不因自检失败而退出；warning 可在日志见到  
- [ ] 概览（或等价 UI）展示 **runtime + 数据目录**  
- [ ] `dashboard_server` 拒绝非 loopback host 常量  
- [ ] README + packaging README 三模式 / 卸载保留 / 便携风险 / loopback 说法一致  
- [ ] pytest：新测 + 全量回归通过；敏感文件名未被 git track  
- [ ] **无** DPAPI/keyring；**无**密钥进 DB；**无**诊断包含 cookies/llm.env 原文  
- [ ] 登录 / LLM 测试保存 / hint / 参与文案 / 退出 行为与改前一致  

---

## 17. 非目标（再次钉死）

- 静态加密、云同步、账号体系  
- 本地 HTTPS、局域网多机访问开关  
- 把 `sources.yaml` / watch 名单当密钥治理  
- 企业 MDM / EDR  
- 方向九更新检查、方向十 MCP  
- 重写整个设置页或强制用户迁移密钥格式  

---

## 18. 实现顺序建议（编码时）

1. `secrets_inventory` + 单测（无行为变化，先对齐 redact/sanitize 引用）  
2. `secure_files` + 挂到 cookie/llm 写点  
3. Cookie / LLM 校验接入写路径  
4. `config_health` + dashboard 入口日志  
5. `assert_loopback_host`  
6. `GET /api/runtime` + 前端卡片  
7. 文档  
8. I1 测试  
9. 全量 pytest + 前端 build  

---

## 19. 编码中禁止的「聪明优化」

| 冲动 | 为何禁止 |
|------|----------|
| 加密「顺便做了」 | 违背 A1；破坏便携 |
| Windows ACL 搞很重导致保存失败 | 违背 C1 |
| 自检失败拒绝启动 | 违背 D1 |
| 统一 redact/sanitize 为同一种匹配 | 改变 job 落库清洗语义 |
| 设置 API 回传明文 key「方便调试」 | 安全回退 |
| 用 `BINGGO_BIND=0.0.0.0` 方便手机调试并写进 README | 违背 G1 |

---

## 20. 状态与检查清单（落地勾选）

| 项 | 状态 |
|----|------|
| 拍板 A–J / ①–⑥ | ✅ 全部按建议 |
| 本文落地规范 | ✅ 成文 |
| P1 编码 | ✅ |
| P2 编码 | ✅ |
| P3 编码 | ✅ |
| 全量验收 §16 | ✅ |

### 实现者自检（合并前）

- [ ] §0 约束未破  
- [ ] §3 inventory 无第二份拷贝列表  
- [ ] §4 harden 失败不阻断  
- [ ] §5/§6 校验只在写严、读宽  
- [ ] §7 自检无网络  
- [ ] §9 loopback 断言  
- [ ] §11 UI 最小  
- [ ] §12 文档三处一致  
- [ ] §16 清单全勾  
- [ ] 全量 `pytest` + `web/frontend` build  

讨论记录：

| 日期 | 内容 |
|------|------|
| 2026-07-20 | 用户确认拍板「全部按建议」；本文成文待编码 |
| 2026-07-20 | P1–P3 编码完成：inventory、权限、校验、自检、runtime API、文档与防泄漏测试 |
