# 方向六：测试与质量 — 落地实现规范

> 状态：**已落地（P1–P5）** — 编码对照本文；验收以 §16 为准  

> 拍板依据：[06-testing-quality.md](./06-testing-quality.md)（**已全部按建议拍板**）  
> 依赖：方向一 DB + `isolated_home`；方向二 SSE；方向三 Job；方向四 `error.code`；方向五 `web/static/dist`  
> 路线图：[fullstack-roadmap.md](../fullstack-roadmap.md) §6  
> 更新：2026-07-19

本文是编码前的最终规范：约束、目录、隔离策略、pytest 补强、vitest 边界、Playwright 五条冒烟（含 mock/夹具/断言）、本地命令、CI YAML、分期与验收。  
**目标红线：**  
1. PR/push CI 稳定阻断坏提交；  
2. 五条冒烟在隔离数据下可复现、零 flaky 进主干；  
3. **不改**产品功能与视觉；CI **不**打外网、**不**读真实密钥。

---

## 0. 约束摘要（不可违背）

| ID | 约束 |
|----|------|
| **Q0** | **不改业务语义**：Job 状态机、SSE 协议、API 路径/错误码表、前端视觉/DOM 冻结点均不动（仅加测试与 CI） |
| **Q1** | 质量层 = **pytest（主力）+ vitest（薄）+ Playwright 冒烟（5 条）**（A2 / F1 / G1） |
| **Q2** | CI / 默认冒烟 **禁止**真扫码、真 Cookie、外网 B 站 / LLM（C1 / J1 / 边角⑦） |
| **Q3** | 自动化数据目录必须隔离：`BINGGO_HOME` → 临时目录；**禁止**读写仓库 `data/binggo.db`（D1） |
| **Q4** | Playwright 权威路径：**先** `npm ci && npm run build`，再对 **FastAPI 托管的 dist** 测（I1） |
| **Q5** | CI 用独立 **`.github/workflows/ci.yml`**；**不**塞进 `release-windows.yml`（E1） |
| **Q6** | pytest 与 Playwright **分命令**；不把 E2E 绑进 pytest 插件（K1） |
| **Q7** | E2E **仅 Chromium**（边角②）；失败上传 trace/screenshot（边角③） |
| **Q8** | **v1 不做** coverage threshold（边角⑥）；不上视觉像素对比 / 多浏览器矩阵 |
| **Q9** | 冒烟进主干：**0 条**已知 flaky；不稳则修到稳或降级为 skip+说明，禁止 `test.fix` 糊弄 |
| **Q10** | 业务规则（筛选 SQL、参与判定、调度撞车等）优先留在 pytest；E2E 只证「页面真跑通」 |

---

## 1. 拍板对照（实现时勿走样）

| 拍板 | 结论 | 实现落点 |
|------|------|----------|
| A | A2 pytest + PW 冒烟 | §5 / §7 / §8 |
| B | B1 五条路径 | §8.3 |
| C | C1 mock 登录 | §6 / §8.2 |
| D | D1 隔离 HOME+DB | §4 / §8.1 |
| E | E1 独立 ci.yml | §11 |
| F | F1 Playwright | §7 |
| G | G1 vitest 薄 | §9 |
| H | H2 补关键洞 | §5 |
| I | I1 dist + FastAPI | §8.1 / §10 |
| J | J1 禁外网 | §6 / §11.4 |
| K | K1 分命令 | §10 |
| ① | PW 在 frontend npm | §3 / §7.1 |
| ② | 仅 Chromium | §7.2 |
| ③ | 失败产物 | §11.3 |
| ④ | 标记 | §5.3 / §7.3 |
| ⑤ | 无 dist skip 静态测；E2E 必 build | §5.4 / §8.1 |
| ⑥ | 无 coverage 门禁 | 不实现 |
| ⑦ | 真 Cookie 仅本地手测 | README 一句即可 |

---

## 2. 目标目录与文件（编码后应存在）

```text
.github/workflows/
  ci.yml                          # 新建：pytest + frontend + e2e

tests/
  conftest.py                     # 已有 isolated_home；可小幅扩展共享 helper（可选）
  test_*.py                       # 已有；按 §5 补洞
  # 可选：tests/helpers/ 放纯 Python 夹具构造（若复用多）

web/frontend/
  package.json                    # 增 @playwright/test、scripts.test:e2e
  playwright.config.ts            # 新建
  e2e/
    smoke.spec.ts                 # 五条冒烟（可拆文件，但首期一个文件即可）
    fixtures/
      seed.ts                     # 或 .mjs：写最小 DB/配置的约定（若用 Python 种子则此可薄）
    helpers/
      app.ts                      # goto、等概览就绪、点侧栏
      mock.ts                     # route 拦截 / 环境约定说明
  # vitest 保持 src/**/*.test.ts

scripts/
  run_e2e_server.py               # 新建：隔离 HOME + 可选测试钩子 + 起 uvicorn
  # 或 e2e 用 playwright webServer 调该脚本

docs/
  plans/06-testing-quality.md
  plans/06-testing-quality-impl.md  # 本文
```

**禁止：**

- 把真实 `cookies.txt` / `llm.env` 拷进 `e2e/fixtures/`  
- 提交 Playwright 浏览器二进制到 git（用 `npx playwright install`）  
- 在 CI 里 `BINGGO_HOME` 指向仓库 `data/`

---

## 3. 依赖与版本

### 3.1 Python（`requirements-dev.txt`）

在现有基础上保持：

```text
-r requirements.txt
pytest>=8.0.0
```

E2E **不**强制加 `pytest-playwright`（K1）。若 `run_e2e_server.py` 只需标准库 + 项目依赖，则不必加新包。  
可选（实现时若需要）：`httpx` 已随 FastAPI/TestClient 存在，勿重复钉死版本除非必要。

### 3.2 前端（`web/frontend/package.json`）

新增 devDependency：

```json
"@playwright/test": "^1.49.0"
```

（实现时锁到当时 npm 解析的精确版并提交 `package-lock.json`。）

新增 scripts：

```json
"test:e2e": "playwright test",
"test:e2e:ui": "playwright test --ui"
```

`engines.node` 保持 `>=20`（与方向五一致）。

### 3.3 CI 系统依赖

- Python **3.12**（与 release 一致）  
- Node **20**  
- Playwright：**仅 Chromium**  
  ```bash
  npx playwright install chromium --with-deps
  ```
  （Linux runner 需要 `--with-deps`；Windows runner 可 `npx playwright install chromium`。）

---

## 4. 数据隔离权威策略（D1）

### 4.1 pytest（已有，保持并遵守）

`tests/conftest.py` → `isolated_home`：

1. `BINGGO_HOME = tmp_path`  
2. patch `src.app_paths` 的 `USER_HOME` / `DATA_DIR` / `CONFIG_DIR`  
3. `reset_engine_for_tests()` + `init_db()`  
4. **断言** `db_path()` 落在 `tmp_path` 下，且 ≠ 仓库 `data/binggo.db`  
5. teardown 再 `reset_engine_for_tests()`

凡新建依赖 DB 的测试：**必须**声明 `isolated_home` fixture（或基于它的派生 fixture）。  
模块级 `TestClient(app)` 且不隔离的旧测：允许保留；**新测不要再扩大「污染风险」写法**。

### 4.2 Playwright / E2E 服务器

每次 E2E 会话：

1. 创建临时目录：`$TMP/binggo-e2e-<随机>`（或 Playwright 的 `testInfo.outputDir` 子目录）。  
2. 环境变量：  
   - `BINGGO_HOME=<临时目录>`  
   - （可选）`BINGGO_E2E=1` — 供 `run_e2e_server.py` / 应用侧识别测试钩子（见 §6.3）  
3. 在该 HOME 下 `init_db()` + 写入最小种子（§8.1）。  
4. 启动 uvicorn 绑定 `127.0.0.1`，端口 **动态**（`0` 或探测空闲端口），避免与开发机 8787 冲突。  
5. 会话结束删除临时目录（失败时可保留 trace，目录可挂在 artifact）。

**硬断言（服务器启动脚本内）：**

```python
assert Path(os.environ["BINGGO_HOME"]).resolve() != (REPO / "data").resolve().parent
# 更直接：db 路径必须在 BINGGO_HOME 下
```

### 4.3 与开发机并行

- 开发者可同时开 `python scripts/run_dashboard.py`（真实数据）与 E2E（临时 HOME + 别的端口）。  
- E2E **不得**默认占用 8787；若 8787 被占，动态端口方案天然避开。

---

## 5. pytest 补强（H2）

### 5.1 原则

- **不**为覆盖率改写生产代码结构。  
- 优先补：契约错误码、门禁、Job 启动拒绝/接受、静态 dist、已有 SSE 测的缺口。  
- 每条新测必须快（通常 &lt; 1s）、无外网。

### 5.2 首期必补清单（编码时逐项打勾）

| ID | 用例意图 | 建议落点 | 断言要点 |
|----|----------|----------|----------|
| P1 | 未登录启动需登录的 job | `tests/test_api_errors.py` 或新建 `test_job_guards.py` | `POST /api/jobs` `refresh_all` → 401 + `AUTH_REQUIRED`；双写 `detail` |
| P2 | 已登录但 LLM 未就绪 | 同上 | `refresh_all` / `participate` → 401 + `LLM_NOT_READY`（mock `get_account_profile` + `is_llm_ready`） |
| P3 | 已就绪可 try_start | 同上 | mock login+llm+`runner.try_start` → 200 `{ok, job}` |
| P4 | 契约头 | 已有则核对；缺则补 | JSON `/api/*` 响应含 `X-Api-Contract: 1` |
| P5 | 静态 dist | 已有 `test_frontend_static.py` | CI 有 dist 时必须跑过；保持 skipif 无 dist |
| P6 | legacy `/app.js` 410 | 已有 | 保持 |

说明：仓库里已有部分门禁测（见 `test_api_errors.py`）；实现时 **先读再补洞**，禁止重复断言冲突。

### 5.3 标记（边角④，可选）

`pytest.ini` 或 `pyproject.toml`：

```ini
[pytest]
markers =
    unit: 纯函数/无 IO
    integration: TestClient / DB / mock 网络
```

首期**不强制**给全部旧文件打标；新文件建议标明。CI 仍跑全量 `pytest -q`。

### 5.4 与 dist 的关系（边角⑤）

- `test_frontend_static`：无 `web/static/dist/index.html` → **skip**（本地未 build 时不挡后端开发）。  
- CI 的 `pytest` job：**建议在 pytest 前执行 frontend build**，或接受静态测 skip、由 `e2e` job 覆盖「打开页面」——**推荐前者**（一次 build，artifact 传给 e2e），见 §11.2。

---

## 6. Mock 与测试钩子（C1 / J1）

### 6.1 pytest 层（既有模式，继续）

```python
with patch("web.app.get_account_profile", return_value={"logged_in": True, ...}):
    with patch("web.app.require_llm_ready")  # 或 patch is_llm_ready
        ...
```

外网：对 `httpx` / 业务 client 使用 `unittest.mock`；**禁止** CI 真请求。

### 6.2 Playwright 层 — 推荐策略（二选一，实现定一种并写死）

#### 策略 α（推荐）：进程内测试钩子 + 最小真实 DB

`scripts/run_e2e_server.py` 在 `BINGGO_E2E=1` 时：

1. 设置隔离 `BINGGO_HOME` 并 `init_db` + seed。  
2. 根据环境变量切换账号/LLM 态，例如：  
   - `BINGGO_E2E_ACCOUNT=logged_out|logged_in`  
   - `BINGGO_E2E_LLM=not_ready|ready`  
3. 用明确、可测的方式注入（任选其一并在实现中单一化）：  
   - **α1**：在仅 E2E 启用的模块里 monkeypatch `web.app.get_account_profile` / `src.llm_settings.is_llm_ready`（启动时 patch）；或  
   - **α2**：写入临时 `cookies.txt`（假内容）+ DB/settings 使 `has_login_cookie`/`is_llm_ready` 为真——**假 Cookie 不得是真实 SESSDATA**。  

路径 3 / 4 通过 **不同 webServer 环境** 或 **同一服务器 + 测试前调内部测试专用 API**（见 α3）切换。

#### 策略 α3（可选增强）：仅 E2E 暴露的测试专用端点

```text
POST /api/testing/e2e-state   # 仅当 BINGGO_E2E=1 注册
Body: { "account": "logged_out"|"logged_in", "llm": "not_ready"|"ready" }
```

- **生产 / 默认启动：不注册该路由**（`run_dashboard.py` 不设 `BINGGO_E2E`）。  
- 实现时放在独立路由器 `web/e2e_hooks.py`，由 `run_e2e_server.py` include。  
- 返回 404 当钩子关闭。  

若担心表面扩大攻击面：钩子仅绑定 `127.0.0.1` 且无钩子时零路由——可接受。  
**拍板允许 α1 或 α3；禁止**在无 `BINGGO_E2E` 时留下测试后门。

#### 策略 β（备选）：Playwright `page.route` 拦截

拦截 `/api/account`、`/api/settings`、`/api/jobs` 等返回固定 JSON。  

| 优点 | 缺点 |
|------|------|
| 不改后端 | 易与真实前端逻辑漂移；SSE `/api/events` 难拦截完整 |
| 切换态快 | 路径 4「真 Job + SSE」变假 |

**结论：** 路径 1/2/5 可用 β；路径 3/4 **优先 α**（真后端门禁 + 真/半真 Job）。首期允许路径 4 对 `runner.try_start` 用短任务 `refresh_status`（需登录+LLM 时按 `_JOB_REQUIRES_*` 核对——`refresh_status` 需登录、**不**需 LLM）。  

查 `web/app.py`：

- `_JOB_REQUIRES_LOGIN`：含 `refresh_all`、`refresh_status`、`participate*` …  
- `_JOB_REQUIRES_LLM`：含 `refresh_all`、`participate*` … **不含** `refresh_status`  

故路径 4 推荐 action：

| 目的 | action | 账号 | LLM |
|------|--------|------|-----|
| 门禁 AUTH | `refresh_status` 或 `refresh_all` | logged_out | * |
| 门禁 LLM | `refresh_all` | logged_in | not_ready |
| 成功启动 | `refresh_status` | logged_in | ready（可不依赖 LLM） |

路径 3 建议拆成两个用例或一个用例内两步（先未登录点「刷新任务状态」，再已登录未 LLM 点「一键更新」）——**仍计为拍板路径 3 的覆盖**，文件内可用两个 `test(...)`。

### 6.3 外网禁用（J1）

E2E 服务器环境建议：

```text
BINGGO_E2E=1
# 可选：若代码有开关
# BINGGO_DISABLE_OUTBOUND=1
```

Job 执行期若仍可能触网：路径 4 应使用 **不会打 B 站的短路径**，或 mock `runner` 工作函数。  
`refresh_status` 若会访问 B 站：则 E2E 中 patch `web.actions` / 对应 refresh 实现为 no-op 成功，或使用 `try_start` 后立即由测试取消——**实现时选一种并在用例注释写明「为何不触网」**。

推荐实现：**E2E 模式下 `refresh_status` 的实际工作函数替换为立即成功的 stub**（仅 `BINGGO_E2E=1`），保证 SSE/`job.terminal` 仍走真实 EventHub 路径。

---

## 7. Playwright 工程配置（F1）

### 7.1 `playwright.config.ts`（语义要求）

路径：`web/frontend/playwright.config.ts`

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,          // 共享一个后端时串行更稳
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,  // CI 允许 1 次重试；本地 0，便于暴露不稳
  workers: 1,                    // 单 worker，避免 HOME/端口打架
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.BINGGO_E2E_BASE_URL, // 由 webServer 或脚本注入
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
    ...devices["Desktop Chrome"],
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "python ../../scripts/run_e2e_server.py",
    // cwd 为 web/frontend 时相对路径如上；实现时用绝对或文档写清
    url: "http://127.0.0.1:PORT/", // 见下：脚本打印 BASE_URL
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
```

**端口约定（必须钉死一种）：**

- **方案 P（推荐）**：`run_e2e_server.py` 固定使用 `127.0.0.1:8791`（专用于 E2E，避开 8787/8181）；启动前若占用则失败并提示。  
- **方案 Q**：动态端口，脚本把 `http://127.0.0.1:<port>` 写到 `e2e/.e2e-base-url` 或环境文件，config 读取。  

首期为简单稳定，**采用方案 P：端口 8791**。  
`baseURL = process.env.BINGGO_E2E_BASE_URL || "http://127.0.0.1:8791"`。

### 7.2 浏览器

```ts
projects: [{ name: "chromium", use: { channel: undefined, ...devices["Desktop Chrome"] } }]
```

仅安装 chromium（边角②）。

### 7.3 标记

```ts
test.describe("smoke", { tag: "@smoke" }, () => { ... });
```

或文件名 `smoke.spec.ts` 即表示冒烟；CI 跑全部 `e2e/` 即可（首期目录只有冒烟）。

### 7.4 选择器纪律（设计零改动友好）

| 优先 | 示例 |
|------|------|
| 现网稳定 `id` / `data-*` | `#section-activities`、`[data-section="activities"]`、`#stats-grid` |
| `getByRole` + 名 | `getByRole("button", { name: "活动" })` |
| 避免 | 易变 class 链、文本正则过宽、nth 依赖布局动画 |

**禁止**为 E2E 去改生产 HTML class/视觉；若必须加钩子，仅允许 `data-testid` 且 **非视觉**——首期尽量不靠新增 testid，优先现网 id。

---

## 8. 五条冒烟详细规格（B1）

### 8.1 种子数据（所有路径共用底座）

在 `BINGGO_HOME` 下至少：

| 项 | 要求 |
|----|------|
| DB | `init_db()` 成功 |
| 活动 | ≥ 3 条（不同 `lottery_type` / `activity_status` 更好）；保证活动页非永久空（路径 2） |
| settings | LLM 表单可读：E2E ready 态下 `is_llm_ready()` 为真的最小条件（按现 `llm_settings` 实现写入临时 `llm.env` 或 DB settings + test passed 标记） |
| cookies | logged_out：无有效 cookie；logged_in：假 cookie 或 hook |

种子实现推荐 **Python**（与 Store/SQLModel 一致），由 `run_e2e_server.py` 调用 `scripts/e2e_seed.py` 或包内函数，避免 TS 直接写 SQLite 与生产 schema 漂移。

### 8.2 服务器脚本 `scripts/run_e2e_server.py`

伪代码职责：

```text
1. 解析/创建 BINGGO_HOME（若未设则 mkdtemp）
2. 断言隔离
3. ensure_user_dirs 或等价；init_db；seed
4. 若 BINGGO_E2E=1：安装 account/llm/job stub（§6）
5. uvicorn.run("web.app:app", host="127.0.0.1", port=8791, log_level="warning")
```

打印一行便于排查：`E2E server on http://127.0.0.1:8791 HOME=...`

**Windows：** 注意 `asyncio` 策略与 `dashboard_server` 一致（可选复用 helper）。

### 8.3 用例规格

#### Smoke-1：打开控制台

| 项 | 内容 |
|----|------|
| 前置 | 默认 seed；account 任意 |
| 步骤 | `page.goto("/")` |
| 断言 | `response` 相关：document 标题含 `Binggo`；`#stats-grid` 或侧栏「概览」可见；`page.locator('script[src*="/assets/"]')` 或 network 中 JS/CSS 自 `/assets/` 且 200；控制台无 **未捕获** 前端异常（可用 `page.on("pageerror")` 收集，期望空） |
| 失败指向 | dist 未挂载 / 前端 main 崩 / CSS 未打进 |

#### Smoke-2：活动列表

| 项 | 内容 |
|----|------|
| 前置 | seed ≥ 3 activities |
| 步骤 | 点击侧栏「活动」`[data-section="activities"]`；等待 `#activities-body` 或卡片列表 |
| 断言 | 活动区标题/副标题区域可见；至少 1 行活动或明确空态文案（有种子时应有行）；点击一个筛选 pill（如「未参加」）不导致白屏；`#pagination` 存在 |
| 失败指向 | 活动 API / 前端 renderActivities |

#### Smoke-3：任务门禁（AUTH + LLM）

| 项 | 内容 |
|----|------|
| 3a AUTH | 状态 `logged_out`；点击「刷新任务状态」或等价 `[data-action="refresh_status"]` |
| 断言 3a | 出现 toast 或可见提示，文案含登录语义；**优先**可通过 UI 看到「请先扫码登录」类 info；network：`POST /api/jobs` → 401，body `error.code === "AUTH_REQUIRED"`（Playwright `page.waitForResponse`） |
| 3b LLM | 切换 `logged_in` + `llm=not_ready`（重启 server 或调用 e2e-state）；点击「一键更新活动链接」`[data-action="refresh_all"]`（若有确认框：点确认） |
| 断言 3b | `error.code === "LLM_NOT_READY"`；toast 为 LLM 测试引导（非把「测试」误匹配到无关文案） |
| 失败指向 | 方向四门禁 / 前端 `notifyJobStartError` |

#### Smoke-4：任务启动成功

| 项 | 内容 |
|----|------|
| 前置 | `logged_in` +（LLM ready 或仅用 `refresh_status`）+ E2E stub 使任务立刻成功 |
| 步骤 | 点击「刷新任务状态」；等待 job 结束 |
| 断言 | `POST /api/jobs` 200；随后 UI：进度条出现过或日志坞可打开且非永久卡死；最终 toast/结果不报未捕获异常；可选：`EventSource` 连上（`/api/events` 200）——用 `waitForResponse` 或服务器日志 |
| 失败指向 | JobRunner / SSE / 前端 realtime |

#### Smoke-5：设置区加载

| 项 | 内容 |
|----|------|
| 前置 | seed settings（参与文案非空或默认；LLM 表单有占位） |
| 步骤 | 留在或回到概览；滚动至「LLM 配置」「参与文案」 |
| 断言 | `#llm-settings-panel` 或既有 id 可见；参与文案输入框可定位；「保存配置」/「保存文案」按钮存在；可选：点击「刷新配置」后 network `GET /api/settings/llm` 200 |
| 失败指向 | settings API / 前端 bind |

### 8.4 用例文件组织

```text
web/frontend/e2e/smoke.spec.ts
```

建议结构：

```ts
test.describe("Binggo smoke @smoke", () => {
  test("1 opens console with hashed assets", ...);
  test("2 activities list and filter", ...);
  test("3a AUTH_REQUIRED on job start", ...);
  test("3b LLM_NOT_READY on refresh_all", ...);
  test("4 job start success path", ...);
  test("5 settings panels load", ...);
});
```

3a/3b 若需不同服务器环境：用 `test.describe.configure({ mode: "serial" })` + beforeAll 调 hook，或拆 project——**首期允许对 3b/4 使用 `test.describe` 级 webServer env**（Playwright 多 project 不同 env）。最简实现：

- **Serial + e2e-state hook（α3）** 切换态，单 server 生命周期。  

---

## 9. vitest（G1）

### 9.1 范围

保持「纯函数 / API client」：

- 已有：`src/api/client.test.ts`（`parseApiErrorPayload`）  
- 允许新增：同样无 DOM 的小函数（如将来抽出的 `mergeAutoLogs`）  
- **禁止**首期用 vitest 挂整页 `jsdom` 测导航

### 9.2 命令

```bash
cd web/frontend && npm test
```

CI `frontend` job 必须执行。

---

## 10. 本地开发者命令（文档须写清）

在 `web/frontend/README.md` 与根 `README.md` 开发者节补充：

```bash
# 后端单测
pip install -r requirements-dev.txt
python -m pytest tests/ -q

# 前端单测 + 构建
cd web/frontend
npm ci
npm test
npm run build

# E2E（会起 8791 隔离服务器）
npx playwright install chromium   # 首次
npm run test:e2e
```

说明：

- E2E 不依赖本机已在跑的 8787 控制台。  
- 真 Cookie 手测仍用 `python scripts/run_dashboard.py`；与 CI 无关。

---

## 11. CI：`.github/workflows/ci.yml`（E1）

### 11.1 触发

```yaml
on:
  pull_request:
  push:
    branches: [main, master]  # 以仓库默认主分支为准；实现时对照 origin
```

### 11.2 Jobs 结构（推荐）

```text
jobs:
  pytest:
    runs-on: ubuntu-latest
    steps: checkout → setup-python 3.12 → pip install → (可选 npm build) → pytest

  frontend:
    runs-on: ubuntu-latest
    steps: checkout → setup-node 20 → npm ci → npm test → npm run build
    # upload-artifact: web/static/dist

  e2e:
    needs: [frontend]
    runs-on: ubuntu-latest
    steps: checkout → setup-python → setup-node → pip install
           → download-artifact dist 到 web/static/dist
           → npm ci（frontend）→ playwright install chromium --with-deps
           → npm run test:e2e
           → 失败时 upload playwright-report / test-results
```

**替代（更简单、稍慢）：** 单 job 顺序跑 pytest → frontend → e2e，免 artifact。首期若求稳可先单 job，再拆。

**拍板要求：** 逻辑上三者都要跑；结构允许单/多 job。

### 11.3 失败产物（边角③）

```yaml
- uses: actions/upload-artifact@v4
  if: failure()
  with:
    name: playwright-report
    path: |
      web/frontend/playwright-report/
      web/frontend/test-results/
```

### 11.4 CI 环境变量

```yaml
env:
  BINGGO_E2E: "1"
  CI: "true"
  # 不要设置指向真实密钥的路径
```

### 11.5 与 release 的关系

- `release-windows.yml`：**不**跑 Playwright；继续负责打包。  
- `ci.yml` 红则不应合入；release 可假设 main 已绿。

---

## 12. `run_e2e_server` 与应用代码改动边界

| 允许 | 禁止 |
|------|------|
| 新增 `scripts/run_e2e_server.py`、`web/e2e_hooks.py`（仅 E2E 注册） | 为测试改 Job 状态机语义 |
| `BINGGO_E2E=1` 时 stub 出站 | 默认开启测试路由 |
| 测试专用 seed 函数 | 把 seed 写进生产 `ensure_user_dirs` 默认路径 |
| 文档与 CI | 改 CSS/HTML 视觉以便「好测」 |

若 stub 必须改 `web/actions.py`：用显式：

```python
if os.environ.get("BINGGO_E2E") == "1":
    ...
```

并加单测或注释保证非 E2E 无行为变化。

---

## 13. 非目标（再次确认）

- Playwright 多浏览器矩阵  
- 视觉回归（Percy/Chromatic 等）  
- 真登录 / 真三连 / 真调度长跑  
- coverage 门禁  
- pytest 内嵌 Playwright  
- 把 E2E 塞进 Windows release 流程  

---

## 14. 分期交付（建议）

| 期 | 内容 | 完成标准 |
|----|------|----------|
| **P1** | `ci.yml`：pytest + frontend test/build | PR 上两者绿 |
| **P2** | pytest 门禁补洞 P1–P4 | 本地 `pytest` 含新断言 |
| **P3** | `run_e2e_server.py` + seed + Playwright 工程骨架 | `npm run test:e2e` 能起浏览器打开 `/` |
| **P4** | Smoke 1–5 全绿；CI e2e job；失败 artifact | 验收 §16 |
| **P5** | README 命令；拍板/路线图状态回写 | 文档一致 |

每期结束：全量 pytest 不得无故变红。

---

## 15. 实现检查清单（编码中自检）

- [x] 未改产品视觉与业务语义  
- [x] `isolated_home` 哲学未破坏；E2E HOME 隔离有断言  
- [x] 无真实 Cookie/Key 进仓库  
- [x] Playwright 仅 Chromium  
- [x] 五条冒烟均有明确 network/UI 断言  
- [x] `BINGGO_E2E` 关闭时无测试后门路由  
- [x] `ci.yml` 独立于 release  
- [x] `package-lock.json` 已更新并提交  
- [x] 本地三套命令可跑通  
- [x] flaky = 0 进主干  

---

## 16. 验收（功能 + 工程）

### 16.1 自动

- [x] `python -m pytest tests/ -q` 全绿  
- [x] `cd web/frontend && npm test && npm run build` 全绿  
- [x] `cd web/frontend && npm run test:e2e` 全绿（5+ 用例）  
- [ ] GitHub Actions `ci` 在 PR 上绿（合入后由 Actions 确认）  

### 16.2 破坏性抽检（实现者做一次）

- [ ] 删掉 `web/static/dist` 后只跑 e2e → 应失败（或 webServer 因无页面失败）  
- [ ] 临时改坏 `parseApiErrorPayload` → vitest 红  
- [ ] 未设 E2E 时用正常 `run_dashboard.py` → 行为与改前一致（无测试路由）  

### 16.3 文档

- [x] README / frontend README 含三套命令  
- [x] 本文件与拍板状态改为已落地（编码完成后）  

---

## 17. 风险与缓解

| 风险 | 缓解 |
|------|------|
| E2E 与开发端口冲突 | 固定 8791 + 占用则失败 |
| Windows 上 Playwright 慢/路径 | CI 以 ubuntu 为主；本地 Windows 文档注明首次 install |
| Job 触网导致红 | E2E stub `refresh_status` 工作函数 |
| SSE 难断言 | 断言 `/api/events` 200 + UI 终态，不解析每一帧 |
| 前端动画导致 click 不稳 | `getByRole` + `await expect(...).toBeVisible()`；必要时 `waitForLoadState("networkidle")` 慎用（SSE 常驻时改用具体 selector） |
| dist artifact 过大 | 只传 `web/static/dist`，不含 node_modules |

---

## 18. 状态

| 项 | 状态 |
|----|------|
| 拍板 | ✅ 全部按建议 |
| 本实现规范 | ✅ 成文 |
| P1–P5 编码 | ✅ 已落地（2026-07-19） |

本地验收：`pytest` 341 passed；`npm test` + `npm run build`；`npm run test:e2e` 6 passed。
