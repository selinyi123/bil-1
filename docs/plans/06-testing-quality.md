# 方向六：测试与质量 — 拍板记录与设计想法

> 状态：**已拍板**；落地实现规范见 [06-testing-quality-impl.md](./06-testing-quality-impl.md)  
> 关联：[全栈路线图 §6](../fullstack-roadmap.md)、[方向四 API 契约](./04-api-contract.md)、[方向五 前端工程化](./05-frontend-engineering.md)、[方向二 SSE](./02-realtime-progress.md)、[方向三 Job](./03-backend-task-model.md)  
> 更新：2026-07-19

本文记录两件事：

1. **拍板结论**（产品/工程边界，已定）  
2. **设计想法**（对照现有 `tests/`、vitest、GitHub Actions 的取舍）

---

## 0. 总前提（已对齐）

| 前提 | 含义 |
|------|------|
| 本地单机控制台 | 测的是本机 FastAPI + 浏览器控制台，**不上**多租户 / 公网压测平台 |
| 底座已稳 | 方向一～五已落地；本方向**不改**业务语义、Job 状态机、SSE 协议、视觉设计 |
| 防回归优先于覆盖率数字 | 目标是「改关键路径会响」，不是追求行覆盖率百分比 |
| 不测真登录 | CI / 默认冒烟**禁止**依赖真实哔哩哔哩扫码或外网 LLM（与路线图非目标一致） |
| 不污染开发机数据 | 自动化一律隔离 `BINGGO_HOME` / 临时库，不得读写仓库真实 `data/binggo.db` |
| 与打包解耦 | Release 装包流程可继续独立；质量门禁以 PR/push CI 为主 |

---

## 1. 拍板结论一览（已定）

| 编号 | 议题 | 结论 | 说明 |
|------|------|------|------|
| **A** | 质量层组合 | **A2** | 加强 pytest + **Playwright 冒烟**；不上视觉回归平台 |
| **B** | 首批冒烟路径 | **B1** | 固定 5 条（见 §2）；可增不可先堆 |
| **C** | 登录 / 鉴权 | **C1** | E2E **mock** 账号与门禁；不做真扫码 CI |
| **D** | 数据隔离 | **D1** | 沿用/扩展 `BINGGO_HOME` + 临时 SQLite + 最小种子 |
| **E** | CI 形态 | **E1** | 新建独立 `ci.yml`（PR/push）；与 release 工作流分离 |
| **F** | 浏览器自动化 | **F1** | **Playwright**（官方推荐栈，与路线图一致） |
| **G** | 前端单测 | **G1** | vitest 保持少量纯函数；UI 路径交给 Playwright |
| **H** | pytest 补强范围 | **H2** | 查漏 Stable API / Job·SSE·错误码；不追求「每个函数一条」 |
| **I** | E2E 怎么起前端 | **I1** | CI：`npm ci && npm run build` 后 FastAPI 托管 `dist` |
| **J** | 外网依赖 | **J1** | CI 内外网 HTTP（B 站 / LLM）一律 mock 或禁用 |
| **K** | 套件划分 | **K1** | pytest 与 Playwright **分命令**；CI 两 job 或同 workflow 两步 |

### 边角（已定）

| 编号 | 议题 | 结论 |
|------|------|------|
| **①** | Playwright 安装 | 进 `web/frontend` 的 npm（`@playwright/test`）；CI `npx playwright install --with-deps`（或 chromium only） |
| **②** | 冒烟浏览器 | **仅 Chromium**（本地单机够用，CI 更快） |
| **③** | 失败产物 | CI 上传 trace / screenshot（失败时）；成功不强制留档 |
| **④** | 测试标记 | pytest：`unit` / `integration`（可选）；Playwright：`@smoke` |
| **⑤** | 与方向五 dist | 无 dist 时：前端静态 pytest **skip**（已有）；Playwright job **必须先 build** |
| **⑥** | 覆盖率门禁 | **v1 不做**强制 coverage threshold |
| **⑦** | 真 Cookie 可选本地调试 | 允许文档写「本地用真实 cookies 手测」；**不进 CI、不进仓库** |

---

## 2. 拍板 B 展开：首批 5 条冒烟（B1）

> 每条都应：**可在隔离数据下稳定复现**、**不依赖真登录/真 LLM**、失败时能指向模块（API / 前端 / 托管）。

| # | 路径 | 断言要点 | Mock / 准备 |
|---|------|----------|-------------|
| **1** | 打开控制台 | `GET /` 200；加载 `/assets/*`；标题/侧栏/概览可见；无前端白屏 | 最小 DB 种子（可空统计） |
| **2** | 活动列表 | 切到「活动」；列表或空态渲染；筛选 pill / 分页控件可点 | 种子若干 `activities` |
| **3** | 任务启动（门禁） | 未登录或 LLM 未就绪时点「一键更新」等 → toast / 契约错误（认 `error.code`） | mock `account` / settings 状态 |
| **4** | 任务启动（已就绪） | mock 登录+LLM 就绪后 `POST /api/jobs` 成功；进度条或日志坞有响应；SSE 或回退轮询不炸 | mock JobRunner 或短任务 `refresh_status` |
| **5** | 设置区只读加载 | 概览 LLM / 参与文案表单有值或占位；保存可走 mock API 200 | mock `/api/settings*` |

**明确首期不做的 E2E：**

- 真扫码登录全流程  
- 真三连参与打到 B 站  
- 定时调度跑完整 cron 窗口  
- 视觉像素对比 / 多浏览器矩阵  

---

## 3. 拍板 C / D：鉴权与数据（实现约束）

### C1 — Mock 登录

- Playwright / 集成测通过 **stub 后端或注入测试账号态**（例如改 `get_account_profile` / 预置 DB + cookie 文件假值），使 UI 呈现「已登录」。  
- 门禁用例（路径 3）与「已就绪」用例（路径 4）分开，覆盖 `AUTH_REQUIRED` / `LLM_NOT_READY` 的 **code 优先** 提示（对齐方向四）。  
- **禁止** CI 读取开发者本机真实 `cookies.txt`。

### D1 — 隔离

- 与现有 `tests/conftest.py` 的 `isolated_home` **同哲学**：`BINGGO_HOME=tmp`、独立 `binggo.db`、断言路径不落仓库 `data/`。  
- Playwright 起 uvicorn/脚本时注入同一环境变量；测完销毁临时目录。  
- 种子数据：最小 JSON/SQL fixture（活动若干条、可选 watch 用户），**不**依赖开发机全量库。

---

## 4. 拍板 E / I / K：CI 与命令

### E1 — 独立 `ci.yml`

触发：`pull_request` + `push`（主分支）。  
Jobs（可合并为顺序 steps，但逻辑分离）：

| Job | 内容 | 失败则 |
|-----|------|--------|
| `pytest` | `pip install -r requirements.txt -r requirements-dev.txt` → `pytest -q` | 阻断合并 |
| `frontend` | `web/frontend`：`npm ci` → `npm test` → `npm run build` | 阻断合并 |
| `e2e` | 依赖 `frontend` 产物；起后端；`playwright test`（Chromium） | 阻断合并 |

**不**塞进 `release-windows.yml`（打包已够重；质量门禁应在合入前完成）。

### I1 — E2E 对着 dist

- 与生产一致：FastAPI 只服务 `web/static/dist`。  
- 避免「Vite dev 能过、打包挂」的盲区。  
- 本地也可 `npm run dev` 手测；**CI 权威路径是 build + dist**。

### K1 — 分命令

```text
python -m pytest tests/ -q          # 后端
cd web/frontend && npm test         # vitest
cd web/frontend && npm run test:e2e # Playwright
```

不把 Playwright 强行塞进 pytest 插件（除非后续有强烈偏好再改）。

---

## 5. 拍板 A / F / G / H / J（取舍摘要）

| 拍板 | 选 | 不选（及原因） |
|------|----|----------------|
| A2 | pytest + Playwright 冒烟 | A1 只加深单测：挡不住「页面挂了」；A3 视觉回归：成本高、与设计冻结收益比低 |
| F1 | Playwright | Cypress/Selenium：生态与路线图已指向 PW；无迁移包袱 |
| G1 | vitest 少而精 | 大面积组件单测：当前无框架组件树，收益低 |
| H2 | 补关键 API/契约/SSE 洞 | 不为覆盖率改生产代码结构 |
| J1 | 禁 CI 外网 | 真网 E2E：脆、慢、密钥风险 |

---

## 6. 此前设计想法（背景，供对照）

以下为拍板前的思路摘要；与上节冲突处以**拍板为准**。

### 6.1 为何做方向六

- 方向一～五连续改存储、任务、推送、契约、前端入口；**手测成本上升**，回归缺口变大。  
- 已有约 **330+** pytest 与少量 vitest，但：  
  - **无** PR 级 GitHub Actions 跑测试（仅有 release / star-history）；  
  - **无**浏览器级冒烟；  
  - 前端工程化后，`dist` 托管与 hash 资源需要一条「打开就亮」的自动证明。

### 6.2 现状盘点（实现时对照）

| 层 | 现状 | 缺口 |
|----|------|------|
| 领域 / Store / 流水线 | `tests/test_*.py` 较全；`isolated_home` 已隔离 DB | 可按失败提高补洞 |
| API / 错误码 / SSE / Job | `test_api_errors`、`test_sse_*`、`test_job_*`、`test_web_api` 等 | Stable 端点与前端双读路径可再钉几条 |
| 前端单元 | `web/frontend` vitest：`parseApiErrorPayload` 等 | 保持薄；复杂交互进 E2E |
| 前端静态托管 | `test_frontend_static`（无 dist 则 skip） | CI 应保证有 dist 再跑 E2E |
| CI | `release-windows.yml` 含前端 build + 打包 | **缺**日常 PR 质量门禁 |

### 6.3 冒烟与「集成测」边界

- **pytest 集成**：`TestClient` / 临时 DB / mock 网络 — 快、稳，继续做主力。  
- **Playwright**：只覆盖「浏览器真加载了 JS/CSS、导航与一次任务反馈」— **薄**、**少**、**稳**。  
- 业务规则（筛选 SQL、参与成功判定、调度撞车）**优先**留在 pytest，不搬进 E2E。

### 6.4 登录策略为何不选真扫码

- 扫码依赖人工与 App，CI 不可复现。  
- Cookie 易过期且属密钥，不能进仓库。  
- 方向四已用 `error.code` 区分门禁；自动化验证 **code → toast/禁用** 比验证「扫码像素」更有价值。

### 6.5 与路线图其它方向

| 方向 | 关系 |
|------|------|
| 4 API 契约 | E2E/API 测认 `error.code`、双读 `detail`；契约变更必须改测 |
| 5 前端工程化 | CI build dist；E2E 打生产入口；vitest 边界保持 J1 |
| 2 / 3 SSE·Job | 路径 4 可断言事件或 UI 进度；协议不改 |
| 7 可观测性 | 本方向可先用现有日志；结构化日志不阻塞六 |
| 8 配置安全 | 测试用假密钥；不把真实 Key 写入 fixture |
| 9 分发 | release 工作流不承担日常 pytest/e2e（E1） |
| 10 MCP | 同一套 REST 测可间接保障；本方向不专测 MCP |

### 6.6 原「百分百 UI 覆盖」— 明确非目标

路线图已写：不追求百分百 UI、不做不稳定真登录 E2E。  
拍板重申：**5 条稳定冒烟 > 50 条脆弱用例**。

---

## 7. 验收红线（实现须满足）

- [ ] PR/push CI 跑通：pytest + frontend test/build + Playwright 冒烟  
- [ ] 5 条冒烟在隔离数据下稳定绿（允许标记 flaky 的不得超过 0 条进主干）  
- [ ] CI 不读真实 `cookies.txt` / `llm.env`，不打外网业务 API  
- [ ] 故意破坏 `dist` 或关键 API 时，对应 job 能红  
- [ ] 开发者文档写清：本地如何跑三套命令  
- [ ] 不改变产品功能与视觉（纯质量向）

细则见落地规范 §16。

---

## 8. 状态

| 项 | 状态 |
|----|------|
| 总前提 | ✅ 已定 |
| 拍板 A–K | ✅ 全部按建议 |
| 边角 ①–⑦ | ✅ 已定 |
| 落地实现规范 | ✅ [06-testing-quality-impl.md](./06-testing-quality-impl.md) |
| 编码 | ✅ 已落地（P1–P5） |

讨论记录：

| 日期 | 内容 |
|------|------|
| 2026-07-19 | 初稿：给出 A–K 与 5 条冒烟建议供拍板 |
| 2026-07-19 | 用户确认：**全部按建议**；落地实现规范成文 |
| 2026-07-19 | P1–P5 编码完成：独立 `ci.yml`、门禁补洞、Playwright 冒烟 6 条本地全绿 |
