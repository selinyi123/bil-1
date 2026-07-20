# Binggo · B 站抽奖助手

在本地运行的 B 站抽奖管理工具：自动从多个 UP 合集和监控用户动态里发现抽奖活动，在网页控制台里一键参与、追踪状态。

> 仅绑定本机 `127.0.0.1`，Cookie 与数据都保存在你的电脑上。

**用户（无需 Python）** → [下载最新安装包](https://github.com/luovicter-collab/bilibinggo/releases/latest)

| 版本 | 说明 |
|------|------|
| Windows 安装包（推荐） | `Binggo-Setup-win64.exe` → 安装后访问 **http://127.0.0.1:8181** |
| Windows 便携版 | 解压 `Binggo-Portable-win64.zip`，双击 `Binggo.exe` |
| macOS（Apple Silicon） | 解压 `Binggo-macOS-arm64.zip`，**右键打开** `Binggo.app` |
| 源码开发 | 先构建前端，再 `python scripts/run_dashboard.py` → **http://127.0.0.1:8787** |

> **Windows：** 安装包未做商业签名；若 SmartScreen 拦截，请选择「仍要运行」。  
> **macOS：** 需要 Apple Silicon（M1+），未做 Apple 公证；首次请右键 → 打开。Intel Mac 请用源码运行。

用户数据目录：Windows `%APPDATA%\Binggo`；macOS `~/Library/Application Support/Binggo`；源码开发为项目根目录。

---

## 打开网站后怎么用

第一次打开控制台，按下面顺序操作即可。左侧边栏有三个页面：**概览**、**数据源**、**活动**。

### 第 1 步：扫码登录

1. 看左侧边栏底部，点击 **「扫码登录」**
2. 用手机哔哩哔哩 App 扫弹窗里的二维码，在手机上确认登录
3. 登录成功后，顶部会显示你的头像和昵称；私信 / @ 未读数也会出现在账号区

> 不登录无法参与活动。Cookie 只保存在本机。

### 第 2 步：配置 LLM（仅转发抽奖需要）

在 **概览** 页面向下滚动，找到 **「LLM 配置」**：

1. 填写 **API Key** 和 **模型名称**（推荐 [DeepSeek](https://www.deepseek.com/) + `DeepSeek-V4-Flash`）
2. 点 **「测试连接」** 确认可用，再点 **「保存配置」**

| 活动类型 | 是否需要 LLM |
|----------|--------------|
| 互动抽奖 | 不需要 |
| 预约抽奖 | 不需要 |
| 转发抽奖 | **需要**（用来解析动态正文里的奖品、开奖时间） |
| 充电抽奖 | 自动跳过，不参与 |

如果暂时只玩互动 / 预约抽奖，可以先跳过这一步。

### 第 3 步：设置参与文案（可选）

仍在 **概览** 页的 **「参与文案」** 区域：

- **自定义文案**：转发和评论时使用你写的内容（默认「好运连连！」）
- **随机借用评论**：从活动评论区第 6～65 条里随机抽一条

建议格式：`@好友昵称 + 一句话`，例如 `@小明 好运连连！`

### 第 4 步：拉取活动

新用户首次打开时，软件已内置：

- **活动库种子**：一批未结束的活跃活动（约 400+ 条），可直接去「活动」页参与
- **数据源检查点**：记录 6 个 UP 合集当前专栏位置，避免把历史合集当成「新专栏」全量爬取（存于本地 SQLite）

> **建议：少用「一键更新活动链接」，优先逐个更新数据源。**  
> 一键更新会并行检查全部 6 个 UP 合集，请求量大，容易触发 B 站风控。日常请在 **数据源** 页，只对需要的合集点 **「更新此源」**。

**推荐做法（数据源页）**

1. 打开左侧 **「数据源」**
2. 在下方 **UP 合集** 列表中，找到想跟进的 UP，点右侧 **「更新此源」**
3. 仅当该 UP 发布了新专栏时，才会拉取新链接并入库

**仅在需要时使用一键更新**（概览 →「一键更新活动链接」）：例如长时间未打开、想一次性扫完全部 6 个源时再用。

**可选：监控用户动态**

1. 在监控名单里填入常转发抽奖的 UP 的 **MID**，点「添加用户」
2. 点 **「更新监控用户动态」**，从他们的近期转发里补充新活动

这是第 7 条发现通道，适合弥补合集漏抓。

### 第 5 步：参与抽奖

切到左侧 **「活动」** 页：

1. 用顶部筛选条缩小范围：类型（互动 / 转发 / 预约）、参加状态（未参加 / 已参加）、关键词搜索
2. 找到想参加的活动，点该行右侧的 **「参与」** 按钮
3. 等待进度条和结果卡片；成功后会标记为「已参加」

**快捷批量：三连参与**

活动列表顶部的 **「三连参与」** 会按当前筛选和排序，自动选取最多 **3** 个「未参加」活动依次参与，适合快速清列表。

| 类型 | 参与时做什么 |
|------|--------------|
| 互动抽奖 | 点赞 → 关注 → 收藏 → 转发 → 评论（评论受限时仍可能算成功） |
| 转发抽奖 | 同上五项，须全部成功 |
| 预约抽奖 | 一键预约，不走五项操作 |
| 充电抽奖 | 不参与 |

### 第 6 步：日常维护

| 你想做什么 | 在哪操作 |
|------------|----------|
| 看看有没有新抽奖 | **数据源** → 单个 UP 合集 **「更新此源」**（推荐）；或概览 **「一键更新」**（慎用） |
| 补充监控 UP 的新转发 | **数据源** →「更新监控用户动态」 |
| 更新参加状态 / 开奖结果 | **活动** 或 **概览** →「刷新任务状态」 |
| 查临近开奖 / 已开奖 | **活动** 页筛选「即将开奖」「已开奖」（±3 天窗口） |
| 看有没有中奖 @ 提醒 | 登录后账号区会显示 @ 未读；增加时会弹横幅，建议去 B 站 **消息中心 → @我的** 核对 |
| 看任务是否出错 | 右下角 **「任务日志」** 坞 |
| 按时间表自动点按钮 | 右上角 **「定时点击」** → 在卡片内 **「启动调度」**（撞车即停，不取消抽奖任务） |
| 检查新版本 / 导出诊断 | **概览** →「检查更新」/「导出诊断包」 |

---

## 界面一览

```
侧边栏
├── 概览      账号、统计、快捷操作、参与文案、LLM、Version / 检查更新
├── 数据源    UP 合集状态、监控用户名单与同步
└── 活动      活动列表、筛选、三连参与、单行参与
```

任务运行时顶部有进度条（SSE 实时推送，断线自动回退轮询）；完成后可能弹出结果卡片或 Toast。

---

## 常见问题

**页面打不开 / 启动失败**

- 安装包请确认访问 **8181**，源码开发用 **8787**
- 若提示端口占用，先关掉其他 Binggo 实例或占用该端口的程序
- Windows 日志：`%APPDATA%\Binggo\data\logs\binggo.log`
- macOS 日志：`~/Library/Application Support/Binggo/data/logs/binggo.log`

**点了参与没反应**

- 确认已扫码登录
- 转发抽奖需先配置并保存 LLM
- 查看右下角任务日志里的报错

**活动列表是空的**

- 先执行「一键更新活动链接」或单源「更新此源」
- 未参加且已过期的活动会自动隐藏（历史仍保留在本地库）

**换电脑 / 重装后数据还在吗**

- Windows：备份 `%APPDATA%\Binggo`（卸载不会自动删除）
- macOS：备份 `~/Library/Application Support/Binggo`（删 `.app` 不会自动删除）
- 核心数据在 `data/binggo.db`；凭证在 `config/cookies.txt`、`config/llm.env`

**页面空白（源码）**

- 需先执行 `cd web/frontend && npm ci && npm run build`，再启动后端

---

## 主要功能

- 6 个 UP 合集 + 监控用户动态，增量发现新活动
- 互动 / 转发 / 预约三类抽奖一键参与，充电抽奖自动跳过
- 三连参与、随机评论文案、临近开奖筛选、定时点击调度
- 消息中心未读与 @ 增长提醒
- 本地 **SQLite**（`data/binggo.db`）主存储；多账号按登录 UID 隔离参与记录与设置
- 长任务 **SSE** 实时进度与日志（断线回退轮询）
- 概览显示 Version / 运行模式 / 数据目录；可手动「检查更新」（仅打开 Releases，不自动安装）
- 「导出诊断包」：脱敏文本，不含 Cookie / API Key 原文

---

## 开发者

需要 **Python 3.12+**；从源码跑控制台还需 **Node.js 20+**（构建前端）。安装包用户不需要 Node。

```bash
git clone https://github.com/luovicter-collab/bilibinggo.git
cd bilibinggo
pip install -r requirements.txt
cd web/frontend && npm ci && npm run build && cd ../..
python scripts/run_dashboard.py   # http://127.0.0.1:8787
```

前端热更新：终端 A 跑后端，终端 B 执行 `cd web/frontend && npm run dev`（见 [web/frontend/README.md](web/frontend/README.md)）。

从旧 JSON 活动库迁移到 SQLite：

```bash
python scripts/import_json_to_db.py
```

| 文档 | 说明 |
|------|------|
| [docs/fullstack-roadmap.md](docs/fullstack-roadmap.md) | 全栈方向 1–9 总览（已落地） |
| [docs/cli.md](docs/cli.md) | 命令行脚本手册 |
| [docs/pipeline-redesign.md](docs/pipeline-redesign.md) | 活动流水线设计 |
| [packaging/windows/README.md](packaging/windows/README.md) | Windows 安装包本地构建 |
| [packaging/macos/README.md](packaging/macos/README.md) | macOS arm64 `.app` 构建与 Gatekeeper |

更新内置种子（维护者）：

```bash
python scripts/export_activities_seed.py
python scripts/export_state_seed.py
```

```bash
# 后端单测
pip install -r requirements-dev.txt
python -m pytest tests/ -q

# 前端单测 + 构建
cd web/frontend
npm ci
npm test
npm run build

# E2E 冒烟（隔离数据目录，端口 8791；首次需装 Chromium）
npx playwright install chromium
npm run test:e2e
```

CI 见 `.github/workflows/ci.yml`（pytest / frontend / Playwright）。真 Cookie 与真实 LLM 仅本地手测，不进自动化。

---

## 隐私与数据目录

| 模式 | 数据根目录 | 密钥位置 |
|------|------------|----------|
| 源码开发 | 仓库根目录 | `config/cookies.txt`、`config/llm.env` |
| Windows 安装包 | `%APPDATA%\Binggo` | 同上相对路径 |
| Windows 便携（`BINGGO_PORTABLE=1`） | `Binggo.exe` 同目录 | 同上；**勿把整个文件夹同步到公开网盘** |
| macOS 默认 | `~/Library/Application Support/Binggo` | 同上相对路径 |
| macOS 便携（`BINGGO_PORTABLE=1`） | `.app` 所在解压目录 | 同上 |
| 自定义 | `BINGGO_HOME` 指向的目录 | `{BINGGO_HOME}/config/...` |

数据根目录下常见布局：

| 路径 | 用途 |
|------|------|
| `data/binggo.db` | 活动、参与、检查点、任务等主库 |
| `data/logs/binggo.log` | JSONL 结构化日志 |
| `config/cookies.txt`、`config/llm.env` | 登录 Cookie / LLM 凭证 |
| `config/sources.yaml` 等 | 数据源与名单配置 |

- 凭证文件已加入 `.gitignore`，仅存本机明文，不会上传到 GitHub
- Windows 卸载 / macOS 删除 `.app` **都不会**自动删除数据目录
- 控制台只监听本机 `127.0.0.1`（开发 `8787` / 安装包 `8181`），请勿改绑局域网地址
- 推送代码前请确认未包含个人凭证与参与记录

---

## 更新日志

### v4.1.0（2026-07-20）

**全栈能力（方向 1–9）**

- 本地 **SQLite**（`data/binggo.db`）作为主存储；提供 JSON → 库导入脚本
- 任务进度 / 日志 **SSE** 实时推送（断线自动回退轮询）
- 统一 Job 模型与任务状态持久化
- API 契约与统一错误体；前端升级为 **Vite + TypeScript**
- JSONL 结构化日志、脱敏诊断包、配置自检与密钥清单
- 概览展示 Version / 运行模式 / 数据目录；手动「检查更新」（不自动安装）
- 新增 **macOS arm64** 安装包（与 Windows Setup / Portable 并列）；版本号单一来源

**安全与稳定**

- 任务日志 / SSE 通道对 Cookie 等字段脱敏
- 定时调度致命错误不再把 traceback 推给前端
- SSE 订阅数上限，避免多标签页撑爆内存

### v4.0.2（2026-07-18）

**控制台体验**

- 侧栏收起 / 展开更丝滑：去掉动画结束时的布局跳动，文字与宽度错峰过渡
- 中等窗口宽度下侧栏不再突然消失；仅 ≤720px 才切为汉堡抽屉
- 日间 / 夜间切换支持页面级柔切（View Transition，不支持时回退短过渡）
- 概览、活动、侧栏与任务日志坞的浅色 / 夜间质感与微交互一并打磨

**稳定性**

- 修复 Windows 上三连并行写活动库时的权限冲突（进程内锁 + 原子写）
- 数据源专栏检查点改为流水线成功后再提交，避免检查阶段提前推进进度
- 错误提示更友好（登录过期、风控限流、LLM 未配置等常见文案）

### v4.0.1（2026-07-17）

**三连参与空列表跳过**

- 本地没有可参与的未参加活动时，三连参与视为正常跳过（`ok` + `skipped`），不再报错
- 定时调度遇到该情况只记日志并继续等待下一刻度，不弹错误、不停机
- 手动点击三连仍会用 info 提示「已跳过」；调度触发的跳过不弹 Toast

### v4.0.0（2026-07-17）

**定时点击监视器（嵌入控制台）**

- 右上角新增「定时点击」悬浮入口，与抽奖控制台同进程运行（8787 / 8181），无需再开独立 8080 服务
- 按时间表自动点击四个按钮：整点刷新批次（一键更新 → 监控动态 → 刷新状态），其余小时每 5 分钟三连参与
- 面板可查看下一刻度倒计时（每秒更新）、下一任务、抽奖任务连通状态与刷新三步时间轴
- 安全底线：撞车即停机、绝不取消正在跑的抽奖任务；「停止调度」只停监视器
- 调度默认不自动启动，需在卡片内手动「启动调度」

**其它**

- DeepSeek 调用默认关闭 thinking，加快结构化抽取
- 补充定时调度安全回归测试

### v3.0.5（2026-07-16）

**开箱即用修复**

- 修复新用户安装后活动统计为 0：启动时主动导入内置活动库，概览/活动页走统一加载逻辑
- 更新内置活动种子至当前未结束活动（约 480 条，含完整详情字段）

### v3.0.4（2026-07-16）

**新用户开箱体验**

- 内置 `state_seed.json`：首次启动写入数据源检查点，避免一键更新误判全量爬取
- 数据源页每个 UP 合集支持 **「更新此源」** 单独增量同步
- README 建议日常优先单源更新，少用一键更新

### v3.0.3（2026-07-16）

- 修复 Windows 安装包启动后 8181 页面空白（无窗口子进程 stdio 问题）
- 明确端口分流：安装包 8181，源码开发 8787

### v3.0.2（2026-07-16）

- 修复打包版启动超时；应用赤陶色图标

### v3.0.1（2026-07-16）

- 首发 Windows 一键安装包与便携版

更早版本见 [GitHub Releases](https://github.com/luovicter-collab/bilibinggo/releases)。

---

## 许可

MIT

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=luovicter-collab/bilibinggo&type=Date)](https://star-history.com/#luovicter-collab/bilibinggo&Date)
