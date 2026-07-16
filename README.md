# bilibili_binggo (Binggo) · v3.0.1

本地运行的 B 站抽奖活动管理工具。自动聚合多个 UP 合集里的抽奖动态，在 Web 控制台里完成同步、筛选、一键参与与状态追踪。

> 仅绑定 `127.0.0.1`，数据保存在本机，适合个人日常使用。

---

## 特性

- **多数据源增量同步**：并行检查 6 个 UP 合集，只处理新增活动链接
- **监控用户动态**：维护 UP 监控名单，扫描其近期转发动态，作为第 7 条发现通道
- **新流水线架构**：采集 → 去重 → 分类 → 详情 → 状态落库，仅新链接走全流程，`skipped` 不入库
- **统一活动库**：`activities_latest.json` 聚合活动数据，兼容读取旧 `enriched` 产物
- **完整活动流水线**：合并去重 → 类型分类 → 详情拉取 → 热度补全 → 状态刷新
- **三类抽奖参与**：互动 / 转发（点赞→关注→收藏→转发→评论）、预约（一键预约）
- **三连参与**：按当前列表筛选与排序，顺序参与最多 3 个「未参加」活动
- **随机评论文案**：可从活动评论区随机抽取转发 / 评论内容
- **临近开奖筛选**：已参加活动中筛选「近 3 天已开奖」或「3 天内即将开奖」
- **消息中心接入**：汇总私信 / 回复 / @ / 赞 / 系统通知未读，@ 增长时提醒查看中奖
- **转发抽奖 LLM 解析**：从动态正文抽取奖品、开奖时间与参与条件
- **Web 控制台**：扫码登录、LLM 配置、活动列表（筛选 / 排序 / 分页）、监控名单、任务日志
- **精致交互与动效**：视图切换过渡、统一按钮 loading、任务日志坞动画、移动端活动卡片
- **多用户隔离**：活动数据全局共用，参与状态与设置按 B 站 UID 分目录存储
- **CLI 全链路**：数据源检查、合并、分类、拉取、参与、消息探针等脚本均可独立运行

---

## 快速开始

### 环境要求

- Python 3.10+
- 可访问 B 站 API 的网络环境

### 安装

```bash
git clone https://github.com/luovicter-collab/bilibinggo.git
cd bilibinggo
pip install -r requirements.txt
```

### 启动控制台

```bash
python scripts/run_dashboard.py
```

浏览器打开 **http://127.0.0.1:8787**

### Windows 用户：下载安装包（无需安装 Python）

适合电脑小白，从 GitHub **Releases** 下载：

| 文件 | 说明 |
|------|------|
| `Binggo-Setup-win64.exe` | 安装版：双击安装，开始菜单 / 桌面快捷方式，安装后点「Binggo」即可 |
| `Binggo-Portable-win64.zip` | 便携版：解压后双击 `Binggo.exe` |

使用步骤：

1. 下载并安装（或解压）
2. 双击 **Binggo** — 浏览器会自动打开控制台
3. 按页面提示扫码登录、配置 LLM（仅转发抽奖需要）

数据保存在 `%APPDATA%\Binggo`（Cookie、活动库、设置）。卸载程序**不会**自动删除该目录，便于保留你的数据。

> 发布新版本：在 GitHub 创建 Release 后会自动构建上述安装包。开发者本地构建见 [packaging/windows/README.md](packaging/windows/README.md)。

### 从源码运行（开发者）

若提示端口占用（Windows PowerShell）：

```powershell
netstat -ano | findstr ":8787"
Stop-Process -Id <PID> -Force
```

### 首次配置（在网页中完成）

| 步骤 | 位置 | 说明 |
|------|------|------|
| 1. 扫码登录 | 侧边栏「扫码登录」 | 用手机 App 扫码，Cookie 自动保存到本地 |
| 2. 配置 LLM | 「设置」→「LLM 配置」 | 仅**转发抽奖**解析需要；互动 / 预约不消耗 LLM |
| 3. 同步活动 | 「概览」→「一键更新活动链接」 | 拉取 DS-1～6 新链接并走新流水线入库 |
| 3b. 监控动态（可选） | 「数据源」→「更新监控用户动态」 | 扫描监控名单近期转发，发现新活动 |
| 4. 参与活动 | 「活动」列表 | 单行「参与」，或使用「三连参与」批量处理 |

**LLM 推荐**：使用 [DeepSeek](https://www.deepseek.com/) 等 OpenAI 兼容接口，模型建议 `DeepSeek-V4-Flash`。在设置页填写 API Key、Base URL、模型名并点「测试连接」。

---

## 使用说明

### 一键更新活动链接

1. 检查 DS-1～DS-6 数据源是否有新专栏 / 视频
2. 与本地活动库去重，仅保留**新链接**
3. 对新链接分类（跳过充电 / 非抽奖 / 失效链接，不落库）
4. 拉取详情与热度；失败时按流水线策略报错或跳过
5. 刷新状态后**一次性落库**到统一活动库

> 设计说明见 [docs/pipeline-redesign.md](docs/pipeline-redesign.md)

### 监控用户动态

在「数据源」页维护监控名单（添加 / 移除 UP 的 MID）。点击「更新监控用户动态」后：

1. 按上次同步时间窗口扫描各 UP 的近期转发
2. 提取其中的活动链接，与本地去重
3. 走与「一键更新」相同的新链接流水线分类、补详情并入库

首次使用可从候选名单导入（见下方 CLI），或在网页中手动添加 MID。

### 活动类型与参与方式

| 类型 | 参与方式 | 说明 |
|------|----------|------|
| 互动抽奖 | 五项操作（评论受限时仍可视为成功） | 走 B 站官方接口 |
| 转发抽奖 | 五项操作须全部成功 | 详情由 LLM 解析 |
| 预约抽奖 | 一键预约 | 仅调用预约接口，不走五项操作 |
| 充电抽奖 | **不参与** | 自动识别并跳过 |

### 三连参与

活动列表顶部的快捷栏，按**当前筛选条件与排序**自动选取最多 **3** 个可参与目标（`未参加` + `can_participate` + 互动 / 转发 / 预约类型）。

- 目标列表会随筛选变化实时更新（类型、关键词、开奖状态、临近开奖窗口等）
- 点击「三连参与」后后台**顺序**执行（降低 B 站限流风险），预约类 1 步、互动 / 转发类各 5 步
- 进度条显示 `当前步/总步`；多活动并行展示为泳道状态
- 结束后弹出结果卡片，逐项展示每个活动的步骤成功 / 失败；全部成功才标记任务成功
- 参与文案（自定义 / 随机评论）与单次参与共用同一套设置

### 参与文案与随机评论

在「设置」→「参与文案」可选择：

| 模式 | 行为 |
|------|------|
| **自定义文案** | 转发与评论使用你填写的固定内容（默认「好运连连！」，最长 233 字） |
| **随机借用评论** | 参与时拉取该动态评论区，跳过前 5 条，从第 6～65 条中随机选一条作为转发 / 评论内容；拉取失败则使用「兜底文案」 |

设置按登录 UID 保存在 `data/users/<uid>/settings.json`（未登录时写入 `config/participate_settings.json`）。

### 临近开奖筛选

针对**你已参加**的活动，按开奖时间 ±3 天窗口筛选：

| 筛选项 | 含义 |
|--------|------|
| **已开奖** | 开奖时间在「现在往前 3 天」至「现在」之间 |
| **即将开奖** | 开奖时间在「现在」至「现在往后 3 天」之间 |

启用临近开奖筛选时会自动忽略「未参加 / 已参加」状态 pill，仅展示符合窗口的已参加活动。列表中「已开奖」行会提示查看 B 站 **@我的** 通知。

「刷新任务状态」完成后，若存在近 3 天已开奖活动，控制台会 Toast 提醒，并在结果中附带 `draw_reminder` 摘要。

### 消息中心与 @ 提醒

登录后账号区异步加载消息未读（不阻塞首屏）：

| 指标 | 说明 |
|------|------|
| 私信未读 | 关注 + 未关注私信会话未读之和 |
| @我的 | 消息中心 @ 未读数；若较上次增加，弹出横幅与 Toast 建议去 B 站查看是否中奖 |
| 其他 | 回复 / 赞 / 系统通知未读汇总在 extras 接口中 |

点击「知道了」会更新本地 `@` 未读基线（`data/users/<uid>/message_watch.json`），避免重复打扰。

命令行完整浏览消息：

```bash
python scripts/check_messages.py
```

---

## 项目结构

```
bilibili_binggo/
├── config/          # 本地配置（首次运行后自动生成，勿提交 Git）
├── data/            # 活动数据与参与记录（默认不提交 Git）
│   ├── output/      # 数据源输出、统一活动库 activities_latest.json 等
│   ├── cache/       # 解析缓存
│   └── users/       # 按 UID 隔离的参与状态、设置、消息基线
├── docs/            # 补充文档（含 pipeline-redesign.md）
├── scripts/         # CLI 入口与维护脚本
├── src/             # 核心业务逻辑
│   ├── activity_store.py   # 统一活动库读写
│   ├── pipeline/           # 一键更新 / 监控新链接流水线
│   ├── watch_users.py      # 监控名单
│   ├── watch_sync.py       # 监控用户动态扫描
│   ├── message_api.py      # B 站消息中心 API
│   ├── message_watch.py    # @ 未读基线与告警
│   ├── draw_reminder.py    # 临近开奖分类与提醒
│   └── participate_text.py # 随机评论文案解析
├── tests/           # 自动化测试
└── web/             # FastAPI 控制台与前端静态资源
```

---

## CLI

详见 [docs/cli.md](docs/cli.md)。

```bash
python scripts/run_dashboard.py              # 启动 Web 控制台
python scripts/bili_login.py                 # 命令行扫码登录
python scripts/check_messages.py             # 查看消息未读与会话
python scripts/discover_watch_users.py       # 从活动转发中发现候选监控 UP
python scripts/maintain_local_activities.py  # 本地活动库维护
```

> 旧版独立脚本 `merge_links.py` / `classify_links.py` / `backfill_heat.py` 已并入流水线；日常请使用控制台或 `run_dashboard.py` 触发任务。

---

## 日志

结构化日志：`data/logs/binggo.log`（单文件最大 5MB，保留 5 份）。

| Logger | 用途 |
|--------|------|
| `binggo.job` | 一键更新、参与、三连参与等后台任务 |
| `binggo.login` | 扫码登录、Cookie 写入 |
| `binggo.fetch` | 活动详情拉取、热度补全 |
| `binggo.api` | B 站 API 请求与回退 |

---

## 开发与测试

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

---

## 隐私与安全

- `config/cookies.txt`、`config/llm.env`、`config/participate_settings.json`、`config/watch_users.json` 已加入 `.gitignore`
- `data/` 运行时数据默认不提交
- Cookie 与 LLM Key 仅存本地，不会上传到仓库
- 控制台仅监听本机 `127.0.0.1:8787`
- 推送代码前请确认未包含个人凭证与参与记录

---

## 更新日志

### v3.0.1（2026-07-16）

**Windows 一键安装**

- 新增 `Binggo-Setup-win64.exe` 安装版与 `Binggo-Portable-win64.zip` 便携版
- 双击启动、自动打开浏览器；用户数据保存在 `%APPDATA%\Binggo`
- GitHub Release 自动构建 Windows 安装包

### v3.0（2026-07-16）

**Windows 安装包（小白用户）**

- 提供 `Binggo-Setup-win64.exe` 安装版与 `Binggo-Portable-win64.zip` 便携版
- 双击即可启动，自动打开浏览器；数据保存在 `%APPDATA%\Binggo`
- GitHub Release 自动构建（见 `packaging/windows/`）

**流水线重设计**

- 一键更新改为「仅处理新链接」五步流水线：采集 → 去重 → 分类 → 详情 → 状态落库
- `skipped`（充电 / 非抽奖 / 失效等）不入库；落库仅在流水线末尾一次性写入
- 新增 `src/pipeline/` 与 `src/activity_store.py` 统一活动库 `activities_latest.json`
- B 站 API 全局限流（`bilibili_rate_limit`）；转发解析与分类缓存版本化

**监控用户动态**

- 数据源页新增监控名单管理（添加 / 移除 MID、同步指标展示）
- 「更新监控用户动态」扫描监控 UP 近期转发，新链接走同一套流水线
- 新增 `discover_watch_users.py` 从活动转发中发现候选 UP

**Web 控制台体验**

- 任务反馈分层（Toast / Banner / 进度条 / inline 表单提示）
- 活动页移动端卡片化、筛选与分页优化
- 动效体系：页面切换过渡、统一按钮 loading、日志坞展开动画
- 视觉精修：暖奶油 + 赤陶主调、衬线标题、卡片景深与微交互

**维护脚本与测试**

- 新增活动库维护、死链清理、详情重建等脚本
- 测试套件扩展至 230+ 用例，覆盖流水线、监控用户、限流与 Web API

### v2.1（2026-07-14）

**消息中心（私信系统）**

- 接入 B 站消息 API：私信 / 回复 / @ / 赞 / 系统通知五类未读汇总
- 账号区展示私信未读与 @ 未读；@ 较上次增加时横幅 + Toast 提醒，可一键跳转 B 站消息中心
- 本地记录 `@` 未读基线，确认后不再重复告警
- 新增 `scripts/check_messages.py` 命令行探针

**临近开奖筛选**

- 已参加活动支持「已开奖」「即将开奖」筛选（开奖时间 ±3 天窗口）
- 刷新任务状态后返回 `draw_reminder` 摘要，并提示查看 @ 通知
- 列表行内 `check_at_recommended` 标记建议核对中奖的活动

**随机评论参与文案**

- 设置页新增「随机借用评论」模式：从评论区第 6～65 条随机抽取转发 / 评论内容
- 拉取失败自动回退兜底文案；参与记录可追踪文案来源（custom / random_comment / custom_fallback）

**三连参与**

- 活动列表快捷栏：按当前筛选顺序最多参与 3 个未参加活动
- 与列表筛选同步（含临近开奖窗口）；顺序执行并展示逐步结果
- 预约抽奖仅走预约流程；成功判定按活动类型区分（不再误用五项操作校验预约类）
- 参与结果居中卡片展示，任务成功须全部活动真实完成

### v2.0（2026-07-14）

**扫码登录（重大更新）**

- 重写 Web 扫码登录流程：分阶段状态（等待扫码 → 已扫码 → 确认中 → 成功/失败）
- 修复二维码 key 不一致导致「扫了码却毫无反应」
- Cookie 原子写入；轮询网络失败自动重试；支持取消登录

### v1.2.1（2026-07-13）

- 预约抽奖热度使用 B 站「预约人数」
- 开奖时间统一为 `YYYY-MM-DD HH:MM` 显示

### v1.2.0（2026-07-13）

- 互动抽奖评论受限时仍可视为参与成功
- 新增「充电抽奖」类型并跳过参与
- 一键更新自动补全缺失热度

### v1.1.0 / v1.0.0

- 六数据源同步、Web 控制台、三类抽奖参与、LLM 解析、多用户隔离、pytest 测试套件

---

## 许可

MIT

---

## Star History

<!-- star-history:start -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/star-history/star-history-dark.svg">
  <img alt="Star history" src="assets/star-history/star-history-light.svg">
</picture>
<!-- star-history:end -->
