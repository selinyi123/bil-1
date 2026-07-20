# 方向五：前端工程化 — 落地实现规范

> 状态：**已落地（P1–P5）** — 编码对照本文；验收以 §15 手测 + 构建产物回归为准  
> 拍板依据：[05-frontend-engineering.md](./05-frontend-engineering.md)（**已全部按建议拍板**）  
> 用户硬性补充：**现在的前端页面的所有设计都不能改变**  
> 依赖：方向二 SSE 行为；方向四 `error.code` / REST 路径；现网 `web/static/{index.html,app.js,styles.css}`  
> 路线图：[fullstack-roadmap.md](../fullstack-roadmap.md) §5  
> 更新：2026-07-19

本文是编码前的最终规范：设计冻结红线、目录与构建、Vite/TS 配置、模块拆分、FastAPI 托管、迁移步骤、打包/CI、测试与分期交付。  
**目标红线：**  
1. **设计零改动** — 视觉、布局、HTML 结构/id/class/文案骨架与现网一致；  
2. **功能不倒退** — 任务/SSE/调度/设置/活动等行为与现网一致；  
3. **工程可维护** — 源码 TypeScript 模块化，生产只跑 `web/static/dist`。

---

## 0. 约束摘要（不可违背）

| ID | 约束 |
|----|------|
| **U0** | **设计零改动（最高优先级）**：禁止改配色、字体层级、间距、圆角、阴影、动效观感、侧栏/主题外观、各坞/横幅/卡片布局；禁止「顺手美化」 |
| **U1** | **HTML 结构冻结**：`index.html` 的标签层级、`id`、`class`、`data-*`、`aria-*`、可见文案骨架须与现网一致（允许的唯一差异见 §2.3） |
| **U2** | **CSS 内容冻结**：`styles.css` **逐字节语义不变**（允许仅因构建工具自动加 hash 文件名 / 压缩空白；**禁止**改选择器语义、禁止 Tailwind/CSS Modules 改写 class） |
| F0 | 技术栈 **Vite + TypeScript**；**不上** Vue/React/Svelte（A1） |
| F1 | 源码根 **`web/frontend/`**；构建输出 **`web/static/dist/`**（D2）；`dist` **不提交 git**（边角①） |
| F2 | 生产 / 打包运行时 **只服务 dist**；禁止长期双入口同时挂旧 `app.js`（B2 / 边角④） |
| F3 | 开发：**Vite HMR + proxy** 到后端（默认 `http://127.0.0.1:8787`）；SSE `/api/events` 必须可流式代理（E1） |
| F4 | `tsconfig`：`strict: true`；允许边界渐进 `any`（F2） |
| F5 | 状态：继续轻量 `state` 对象；不上 Redux/Pinia/Zustand（G1） |
| F6 | CSS：整文件接入；**不拆视觉文件、不重写样式**（H1 + U2） |
| F7 | Node **20 LTS**；包管理器 **npm**（边角②③） |
| F8 | `packaging/windows/build.ps1` 与 release CI：**先** `npm ci && npm run build`，失败则中止打包（I2） |
| F9 | 本方向测试：vitest 仅覆盖纯函数 / API client；**不上** Playwright（J1） |
| F10 | SSE：独立模块；行为对齐方向二（心跳、H2 回退、`finishJobOnce` 等）；**不改**事件协议（K1） |
| F11 | **不改**后端业务语义、Job 状态机、API 路径与错误码表 |
| F12 | 动态插入 DOM 的 HTML 字符串（活动卡片等）须保持现网 class/结构；禁止换皮肤式 class |

---

## 1. 拍板对照（实现时勿走样）

| 拍板 | 结论 | 实现落点 |
|------|------|----------|
| 用户硬性 | 设计零改动 | §2 全文；§15 视觉验收 |
| A | A1 Vite+TS 无框架 | §3 / §4 |
| B | B2 一次切源 | §6 迁移；§7 切除旧入口 |
| C | C1 + 冻结 | §2 |
| D | D2 `static/dist` | §3.2 / §8 |
| E | E1 proxy | §5 |
| F | F2 strict | §4.2 |
| G | G1 state | §6.3 |
| H | H1 整 CSS 原样 | §2.2 / §4.3 |
| I | I2 打包强制 build | §9 |
| J | J1 少测 | §12 |
| K | K1 realtime 模块 | §6.4 |
| ① | dist 不入库 | `.gitignore` |
| ④ | 旧 app.js 归档 | §7 |

---

## 2. 设计零改动 — 权威细则（U0–U2）

> 本方向是 **搬仓库房**，不是 **装修门面**。任何「看起来更现代一点」的改动都视为违规。

### 2.1 冻结清单（禁止改）

| 类别 | 冻结内容 |
|------|----------|
| 视觉 | 颜色、渐变、字体族与字号阶梯、行高、间距、圆角、边框、阴影、透明度、模糊 |
| 布局 | 栅格、侧栏宽、坞位置与尺寸、横幅结构、卡片排列、响应式断点行为 |
| 动效 | 现有 CSS/JS 动效的时长与缓动观感（逻辑搬迁时保持同类调用） |
| HTML | 元素顺序与嵌套；所有 `id` / `class` / `data-*` / `aria-*`；按钮文案与标题文案（业务动态文案除外） |
| CSS | 选择器与声明块语义；禁止改写成 CSS Modules / scoped 哈希 class |
| 资源 | `favicon.svg` 不变；Google Fonts 外链可保留（现网已有） |

### 2.2 CSS 策略（H1）

1. 将现网 `web/static/styles.css` **原样复制**到前端工程（推荐路径：`web/frontend/src/styles/styles.css` 或 `web/frontend/styles.css`）。  
2. 在 `main.ts` 中：`import "./styles/styles.css"`（或等价），让 Vite 打进产物。  
3. **禁止**：拆文件改视觉、重命名 class、引入预处理器「优化」、改 CSS 变量主题值。  
4. 允许：Vite/cssnano 做空白压缩（若开启）；**比较验收**时用「渲染观感一致」而非「源文件字节全同」。  
5. 主题（light/dark）与侧栏折叠：继续写 `documentElement` / `localStorage` 现网键名（如 `binggo-theme`、`binggo-sidebar-collapsed`），逻辑搬迁不改键名。

### 2.3 HTML 策略（U1）

1. 以现网 `web/static/index.html` 为唯一真相，复制为 Vite 入口 `web/frontend/index.html`。  
2. **允许的唯一结构性差异**（仅为接入构建）：  
   - 去掉手写 `?v=20260718b8` 的 `/styles.css`、`/app.js` 引用；  
   - 改为 Vite 约定：`<script type="module" src="/src/main.ts"></script>`，样式由 JS import 注入（dev）或 build 注入 link（prod）。  
3. **禁止**：增删区块、改 id/class、调整 DOM 顺序、改 `hidden` 初始状态、改确认框/二维码模态结构。  
4. `<head>` 内联的 sidebar 防闪脚本：**原样保留**（逻辑与 class `sidebar-init-collapsed` 不变）。  
5. build 后 dist 内 `index.html` 由 Vite 生成：asset 路径可为 `/assets/xxx-[hash].js`；**body 内业务 DOM 必须与源入口一致**。

### 2.4 JS 与设计的边界

| 允许 | 禁止 |
|------|------|
| 把函数拆到模块；加类型 | 为「好维护」改 DOM API 调用方式导致结构变（如换 innerHTML 模板皮肤） |
| 保持现有 `escapeHtml` / 模板字符串 class | 换成新的 BEM 命名或 utility class |
| 修正明确 bug（行为错误） | 借机改 toast 样式、按钮尺寸、颜色 token |

动态渲染（活动列表项、toast、确认框内容等）：**对照现网字符串模板逐段迁移**，class 名必须一致。

### 2.5 设计验收方法（编码后必做）

1. 同一后端数据下，旧入口（切换前 backup）与新 dist **并排或前后截图对比**关键页：概览、活动、设置、任务运行中、调度坞打开、扫码模态。  
2. 侧栏折叠 / 主题切换后观感一致。  
3. 浏览器缩放到常见宽度（桌面 + ≤720px）布局不坏且与现网一致。  
4. 若有争议：**以切换前 `web/static` 备份为权威**。

---

## 3. 目录与构建产物

### 3.1 目标树

```text
web/frontend/                    # 前端工程根（源码，提交 git）
  package.json
  package-lock.json
  vite.config.ts
  tsconfig.json
  tsconfig.node.json
  index.html                     # 从 static/index.html 复制并只改资源入口
  src/
    main.ts                      # 入口：import 样式 + init()
    state.ts
    types/                       # Job / ApiError 等轻量类型
    api/
      client.ts                  # fetchJSON + error.code
      paths.ts                   # 可选：路径常量
    realtime/
      sse.ts                     # EventSource + H2 回退
    jobs/                        # 进度条、日志坞、完成、二维码登录
    activities/                  # 列表、筛选、三连、参与
    auto/                        # 调度坞
    account/                     # 账号、onboarding
    settings/                    # LLM、参与文案
    watch/                       # 监控用户
    shell/                       # nav、theme、toast、confirm、sidebar
    styles/
      styles.css                 # 现网 styles.css 原样
    utils/                       # escapeHtml、sanitize、format 等
  vitest.config.ts               # 可选，J1

web/static/
  dist/                          # npm run build 输出（不提交）
    index.html
    assets/*
  favicon.svg                    # 可继续放在 static 根，由 FastAPI 提供
  backup_pre_frontend/           # 切换时归档旧 index.html/app.js/styles.css（可选）

web/app.py                       # 改为托管 dist（§8）
```

### 3.2 Vite `build` 配置要求

```ts
// vite.config.ts 关键项（语义必须满足）
export default defineConfig({
  root: ".", // web/frontend
  base: "/", // 资源绝对路径，适配 FastAPI 根路径托管
  build: {
    outDir: "../static/dist",
    emptyOutDir: true,
    assetsDir: "assets",
    sourcemap: true, // 建议开，便于排查；若嫌体积可仅 CI 开
  },
  server: {
    port: 5173,
    proxy: { /* §5 */ },
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
});
```

### 3.3 `.gitignore` 增补

```gitignore
web/frontend/node_modules/
web/static/dist/
```

不忽略：`web/frontend/package-lock.json`（应提交以保证 CI 可复现）。

### 3.4 npm scripts（最低集）

| script | 作用 |
|--------|------|
| `dev` | `vite` |
| `build` | `tsc --noEmit`（或 `vue-tsc` 无）+ `vite build`；建议 `npm run typecheck && vite build` |
| `preview` | `vite preview`（可选） |
| `test` | `vitest run`（J1） |

---

## 4. TypeScript 与代码风格

### 4.1 与仓库风格对齐

- 沿用现网命名：`camelCase` 函数、现有 `state` 字段名不重命名。  
- 不引入新的代码风格工具强制全文件 reformat（若加 prettier，**配置为尽量贴近现状**，避免巨型无关 diff；实现期可先不加）。  
- 模块使用 ESM `import`/`export`。

### 4.2 `tsconfig`（F2）

- `"strict": true`  
- `"moduleResolution": "bundler"`  
- `"target": "ES2020"` 或 Vite 默认  
- `"noEmit": true`（若用 `tsc` 只做检查）  
- 允许：`skipLibCheck: true`  
- DOM lib 开启  

类型优先覆盖：

| 类型 | 用途 |
|------|------|
| `ApiError` | `code`, `httpStatus`, `detail`, `message` |
| `JobStatus` | 对齐 `JobStatus.to_dict()` / 方向三字段 |
| `AutoStatus` | 调度 status 主要字段（次要可 `Record<string, unknown>`） |

**不做** OpenAPI 自动生成（边角⑤）。

### 4.3 样式接入（再强调）

仅 `import "@/styles/styles.css"`（路径按实际）；禁止 CSS Modules（`*.module.css`）。

---

## 5. 开发联调（E1）

### 5.1 进程模型

```text
终端 A: python scripts/run_dashboard.py     # 后端 API +（生产态）dist
终端 B: cd web/frontend && npm run dev      # Vite :5173
浏览器打开 Vite URL（开发时）
```

开发期也可暂时让 FastAPI 不托管前端，只当 API；以 Vite 为页面入口。

### 5.2 Proxy 规则（必须）

```ts
proxy: {
  "/api": {
    target: "http://127.0.0.1:8787",
    changeOrigin: true,
    // SSE：勿缓冲
  },
  // 二维码图片等
  "/api/login/qrcode": { target: "http://127.0.0.1:8787", changeOrigin: true },
}
```

说明：`/api` 已覆盖 qrcode。若现网端口不是 8787，以 `run_dashboard.py` / 文档实际端口为准，**写入 `vite.config.ts` 注释与 frontend README**。

### 5.3 SSE 验收（dev）

- Network 中 `/api/events` 为 `text/event-stream`，能收到 `heartbeat` / `job.*` / `auto.*`。  
- 断开后端时前端按 H2 回退轮询（行为与现网一致）。

### 5.4 生产预览

```bash
npm run build
python scripts/run_dashboard.py
# 浏览器打开控制台地址，确认加载的是 /assets/*-[hash].js
```

---

## 6. 模块拆分规范

### 6.1 原则

1. **先搬后净**：优先原样迁移逻辑，再小步去重；禁止借重构改行为。  
2. **按域切开，按调用关系分层**：`api` / `realtime` 不依赖具体 DOM 视图；视图模块可依赖 `state` + `api`。  
3. **单一入口**：`main.ts` 只做 `import "./styles/..."` + 调用 `init()`（现网 `init` 逻辑）。  
4. **不改函数对外行为**：现网函数名可保留（便于对照 diff）；若重命名须全局替换且测全。

### 6.2 推荐模块地图（可微调文件名，职责勿混）

| 模块 | 迁入内容（来自现 app.js） |
|------|---------------------------|
| `api/client.ts` | `fetchJSON`、错误码挂载 |
| `realtime/sse.ts` | `startRealtime`、`fallbackToPolling`、`handleSseMessage`、watchdog |
| `jobs/*` | 进度条、日志坞、`finishJobOnce`、`handleJobCompletion`、二维码登录 |
| `auto/*` | 调度坞、倒计时、启停 |
| `activities/*` | 列表、筛选、三连预览、参与按钮 |
| `settings/*` | LLM、参与文案 |
| `watch/*` | 监控用户 |
| `account/*` | 账号区、onboarding |
| `shell/*` | 导航、主题、侧栏、toast、confirm |
| `state.ts` | `const state = { ... }` |
| `utils/*` | `escapeHtml`、`sanitizeUserText`、时间格式等 |

### 6.3 `state`（G1）

- 保持**一个**可变 `state` 对象（或 `state` + 少量模块私有状态）。  
- 字段名与现网一致（`currentJob`、`sseHealthy`、`autoLogs` 等）。  
- 不引入不可变 store 模式，除非零行为变化且必要（默认不做）。

### 6.4 realtime（K1）

必须保持的行为点（对照方向二 impl / 现网审查后代码）：

- EventSource 订阅事件名集合不变  
- 心跳与 watchdog  
- H2：不健康时 Job/Auto 回退轮询；恢复后停 REST 轮询（倒计时保留）  
- `finishJobOnce` 去重  
- `no-eventsource` 不死循环重连  
- auto.log 与 snapshot 合并去重逻辑保留  

### 6.5 api/client（方向四对齐）

- 继续双读：`error.message` → 顶层 `detail`  
- `Error` 上挂 `code` / `httpStatus` / `detail`  
- 启动任务 toast：**code 优先**（`AUTH_REQUIRED` / `LLM_NOT_READY`），避免过宽 `includes("测试")`

---

## 7. 旧资源切换策略（B2 / 边角④）

### 7.1 切换顺序（实现者执行）

1. 建 `web/frontend` 工程；复制 HTML/CSS；搭通 `dev` + proxy。  
2. 分域把 `app.js` 迁成 TS，直到 `npm run build` 成功且手测通过。  
3. 改 `web/app.py` 托管 `static/dist`（§8）。  
4. 将旧 `web/static/index.html`、`app.js`、`styles.css` **移到** `web/static/backup_pre_frontend/`（或 `data/backup/...`），**运行路径不再读取**。  
5. 保留 `web/static/favicon.svg`（及 dist 未包含的静态小资源）的服务方式。  
6. 更新打包脚本（§9）；跑一次 windows build 或至少 `npm run build` + 本地 dashboard。  
7. 文档：`README` / packaging README 注明需 Node 20 才能从源码构建前端。

### 7.2 禁止

- FastAPI 同时提供旧 `/app.js` 与 dist 入口导致「改了源看不到」。  
- 把未构建的 `web/frontend/src` 直接给浏览器加载（生产）。

---

## 8. FastAPI 托管改造（D2）

### 8.1 目标行为

| 请求 | 响应 |
|------|------|
| `GET /` | `web/static/dist/index.html` |
| `GET /assets/*` | dist 内 hash 资源 |
| `GET /favicon.svg` | `web/static/favicon.svg`（或拷贝进 dist，二选一，实现时定一种） |
| `GET /api/*` | 现有 API（不变） |
| `GET /app.js` / `GET /styles.css` | **删除或 410**；勿再指向旧巨石文件 |

### 8.2 推荐实现要点

```python
DIST_DIR = WEB_DIR / "static" / "dist"
STATIC_DIR = WEB_DIR / "static"

# 1) API 路由保持
# 2) 显式 FileResponse favicon（若需要）
# 3) mount StaticFiles(DIST_DIR) 或对 HTML5 history 回退 index.html
# 4) 若 dist 不存在：启动日志明确报错「请先 npm run build」
```

注意：

- 现网 `StaticFiles(..., html=True)` 挂在 `/` 会吃掉未匹配路由；改造后须保证 **API 注册在 mount 之前**（现已如此）。  
- SPA 回退：本项目无前端路由框架，多为单 `index.html`，一般 **不需要** 任意路径回退；直接提供 `/` 即可。  
- 缓存：hash 资产可 `Cache-Control: max-age=...`；`index.html` 建议 `no-cache` 或短缓存，避免旧 HTML 指到已删 hash。

### 8.3 开发体验提示

`run_dashboard.py` 可检测 `dist` 缺失时打印：

```text
未找到 web/static/dist。开发请另开: cd web/frontend && npm run dev
生产请先: cd web/frontend && npm ci && npm run build
```

（文案可微调，语义必须有。）

---

## 9. 打包与 CI（I2）

### 9.1 `packaging/windows/build.ps1`

在 PyInstaller **之前**插入：

```powershell
Write-Host "==> 构建前端"
Push-Location (Join-Path $Root "web\frontend")
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "需要 Node.js/npm（建议 Node 20）" }
npm ci
npm run build
Pop-Location
if (-not (Test-Path (Join-Path $Root "web\static\dist\index.html"))) {
    throw "前端构建失败：缺少 web/static/dist/index.html"
}
```

### 9.2 `binggo.spec`

继续收集 `web/static`（内含 `dist/` + favicon）。**不要**打包 `web/frontend/node_modules`。  
确认 datas 路径在改托管后仍指向正确 static 根。

### 9.3 GitHub Actions

`release-windows.yml`（及同类）：`actions/setup-node@v4` with `node-version: 20`，再 `npm ci && npm run build`，然后现有 Python 打包步骤。

### 9.4 便携版说明

安装包用户**不需要** Node；Node 只是**从源码构建**的依赖。README 写清这一点。

---

## 10. 与 pytest / 后端测试

- 后端 pytest **不依赖**浏览器；但若测试里 `TestClient` 访问 `/` 或旧 `/app.js`，须更新断言：  
  - `/` → 200 且为 dist HTML（测试环境需先 build，或 skip/mock）  
  - 推荐：对静态页测试加 `@pytest.mark.skipif(not dist.exists())` 或 fixture 生成最小 dist  
- **禁止**让全量 pytest 强依赖 `npm run build`（过慢）；静态测试可独立标记。

---

## 11. 非目标（再次确认）

- 任何视觉/HTML/CSS 设计改动（U0）  
- Vue/React、Tailwind、CSS Modules 换肤  
- Playwright E2E（方向六）  
- OpenAPI → TS 全量生成  
- 改 SSE 协议或后端 API  
- 提交 `node_modules` / `dist`  

---

## 12. 测试清单（本方向）

### 12.1 vitest（J1，建议最低）

- [ ] `fetchJSON`：解析 `error.code` + 兼容 `detail` 字符串  
- [ ] 可选：`autoLog` 合并去重纯函数（若已抽出）  

### 12.2 手工 / 构建

- [ ] `npm run build` 成功  
- [ ] 生产模式打开控制台：功能清单 §15  
- [ ] 设计对比 §2.5  
- [ ] Vite dev：SSE 通；代理 API 通  

---

## 13. 分期交付（建议）

| 期 | 内容 | 完成标准 |
|----|------|----------|
| **P1** | 脚手架：`web/frontend`、Vite/TS、CSS/HTML 原样接入、proxy、空 `main.ts` 能显示**完整静态页**（无逻辑也可先挂空 init） | 设计对比通过；dev 能打开与现网同 DOM 的页面 |
| **P2** | 迁 `api` + `shell`（toast/nav/theme）+ `state`；页面可点导航 | 无控制台报错 |
| **P3** | 迁 `jobs` + `realtime`（含 H2） | 任务/SSE/登录扫码手测过 |
| **P4** | 迁 `activities` + `auto` + `settings` + `watch` + `account` | 全功能手测过 |
| **P5** | 切 FastAPI → dist；归档旧 static；打包脚本 + CI Node；gitignore | 生产唯一入口；旧 app.js 不再被引用 |

每期结束都做一次 **§2.5 设计抽检**，防止漂移。

---

## 14. 实现检查清单（编码中自检）

- [ ] 未改 `styles.css` 视觉声明  
- [ ] `index.html` 业务 DOM 与备份一致（除资源入口）  
- [ ] 动态 HTML 模板 class 未改名  
- [ ] 无 Vue/React/Tailwind  
- [ ] `npm run build` → `web/static/dist/index.html` 存在  
- [ ] FastAPI 不再挂载旧巨石 `app.js`  
- [ ] dev proxy 下 `/api/events` 流式正常  
- [ ] `error.code` 分支仍在  
- [ ] windows build 脚本含前端 build  
- [ ] `dist/`、`node_modules/` 已 gitignore  

---

## 15. 手测验收（功能 + 设计）

### 15.1 设计（必须）

- [ ] 概览首屏观感与现网一致  
- [ ] 活动页 / 设置页 / 侧栏折叠 / 暗色主题一致  
- [ ] 任务进度横幅、日志坞、结果条、调度坞、扫码模态一致  
- [ ] 无新增「设计感」元素或错位  

### 15.2 功能（必须）

- [ ] 登录扫码、取消  
- [ ] 一键更新 / 监控 / 状态刷新  
- [ ] 活动筛选、分页、三连预览与参与  
- [ ] SSE 进度 + 断线回退  
- [ ] 调度启停与倒计时  
- [ ] LLM / 参与文案保存与测试  
- [ ] 监控用户增删  
- [ ] 硬刷新后资源 200（hash 资产）  
- [ ] 未登录 / LLM 未就绪 toast 仍正确（认 code）  

---

## 16. 状态

| 项 | 状态 |
|----|------|
| 拍板 | ✅ 全部按建议 + 设计零改动 |
| 本实现规范 | ✅ 成文 |
| P1–P5 编码 | ✅ 已落地（`web/frontend` → `web/static/dist`；旧资源见 `web/static/backup_pre_frontend/`） |

全部验收后回写路线图 §5。
