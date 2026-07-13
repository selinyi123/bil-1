# bilibili_binggo (Binggo)

本地运行的 B 站抽奖活动管理工具。自动聚合多个 UP 合集里的抽奖动态，在 Web 控制台里完成同步、筛选、一键参与与状态追踪。

> 仅绑定 `127.0.0.1`，数据保存在本机，适合个人日常使用。

---

## 特性

- **多数据源增量同步**：并行检查 6 个 UP 合集，只处理新增活动链接
- **完整活动流水线**：合并去重 → 类型分类 → 详情拉取 → 热度补全 → 状态刷新
- **三类抽奖参与**：互动 / 转发（点赞→关注→收藏→转发→评论）、预约（一键预约）
- **转发抽奖 LLM 解析**：从动态正文抽取奖品、开奖时间与参与条件
- **Web 控制台**：扫码登录、LLM 配置、活动列表（筛选 / 排序 / 分页）、单行参与、任务日志
- **多用户隔离**：活动数据全局共用，参与状态按 B 站 UID 分目录存储
- **CLI 全链路**：数据源检查、合并、分类、拉取、参与等脚本均可独立运行

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

若提示端口占用（Windows PowerShell）：

```powershell
netstat -ano | findstr ":8787"
Stop-Process -Id <PID> -Force
```

### 首次配置（在网页中完成）

无需手动编辑配置文件，按以下顺序在控制台操作即可：

| 步骤 | 位置 | 说明 |
|------|------|------|
| 1. 扫码登录 | 侧边栏「扫码登录」 | 用手机 App 扫码，Cookie 自动保存到本地 |
| 2. 配置 LLM | 「设置」→「LLM 配置」 | 仅**转发抽奖**解析需要；互动 / 预约不消耗 LLM |
| 3. 同步活动 | 「概览」→「一键更新活动链接」 | 拉取新链接、补全详情与热度 |
| 4. 参与活动 | 「活动」列表 | 可按热度排序，单行点击「参与」 |

**LLM 推荐**：使用 [DeepSeek](https://www.deepseek.com/) 等 OpenAI 兼容接口，模型建议 `DeepSeek-V4-Flash`（便宜、够快，适合 JSON 抽取）。在设置页填写 API Key、Base URL、模型名并点「测试连接」。

未配置 LLM 时，转发抽奖可能缺少奖品 / 开奖时间字段，互动与预约类活动不受影响。

---

## 使用说明

### 一键更新活动链接

执行完整同步流程：

1. 检查 DS-1～DS-6 数据源是否有新专栏
2. 合并去重、分类抽奖类型
3. 拉取缺失的活动详情，并**自动补全缺失的热度（转发数）**
4. 刷新「已参加 / 未参加 / 已结束」状态

无新链接时也会补全本地尚未确认热度的历史活动，无需单独操作。

### 活动类型

| 类型 | 参与方式 | 说明 |
|------|----------|------|
| 互动抽奖 | 五项操作（评论受限时仍可视为成功） | 走 B 站官方接口 |
| 转发抽奖 | 五项操作须全部成功 | 详情由 LLM 解析 |
| 预约抽奖 | 一键预约 | 走 B 站官方接口 |
| 充电抽奖 | **不参与** | 自动识别并跳过 |

### 参与文案

在「设置」中可自定义转发 / 评论文案（默认「好运连连！」），建议格式：`@好友昵称 + 一句话`。

---

## 项目结构

```
bilibili_binggo/
├── config/          # 本地配置目录（首次运行后自动生成，勿提交 Git）
├── data/            # 活动数据与参与记录（默认不提交 Git）
│   ├── output/      # 合并 / 分类 / 详情等共用数据
│   ├── cache/       # 解析缓存
│   └── users/       # 按 UID 隔离的参与状态
├── docs/            # 补充文档
├── scripts/         # CLI 入口
├── src/             # 核心业务逻辑
├── tests/           # 自动化测试
└── web/             # FastAPI 控制台与前端静态资源
```

---

## CLI

命令行可独立完成与 Web 相同的流水线步骤，详见 [docs/cli.md](docs/cli.md)。

常用示例：

```bash
python scripts/run_dashboard.py      # 启动 Web 控制台
python scripts/bili_login.py         # 命令行扫码登录（也可在网页完成）
python scripts/backfill_heat.py      # 单独补全活动热度
```

---

## 日志

运行控制台后，结构化日志写入 `data/logs/binggo.log`（自动轮转，单文件最大 5MB，保留 5 份）。

日志模块划分：

| Logger | 用途 |
|--------|------|
| `binggo.job` | 一键更新、参与等后台任务 |
| `binggo.fetch` | 活动详情拉取、热度补全 |
| `binggo.api` | B 站 API 请求与回退 |
| `binggo.api` (web) | FastAPI 服务 |

排查参与失败、热度补全异常时，优先查看该文件。

---

## 开发与测试

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

---

## 隐私与安全

- `config/cookies.txt`、`config/llm.env`、`data/` 已加入 `.gitignore`
- Cookie 与 LLM Key 仅存本地，不会上传到仓库
- 控制台仅监听本机 `127.0.0.1:8787`，不对外暴露服务
- 推送代码前请确认未包含个人凭证与参与记录

---

## 更新日志

### v1.2.1（2026-07-13）

**热度**

- 预约抽奖热度改为使用 B 站页面的「预约人数」，与官网展示一致（不再误用转发数）
- 一键更新会自动刷新尚未迁移的旧预约活动热度

**开奖时间**

- 统一显示为 `YYYY-MM-DD HH:MM`
- 支持解析 `7月15号` 等格式；无法确定的相对时间（如「下周」）显示为 `—`

### v1.2.0（2026-07-13）

**参与与分类**

- 互动抽奖：评论因「关注 UP 主 7 天以上」等限制失败时，其他操作成功仍视为参与成功
- 新增「充电抽奖」类型，一律不参与
- 参与时捕获「无法获取动态详情」，避免任务崩溃

**热度与同步**

- 一键更新在无新链接时也会补全缺失热度
- 自动重置错误的热度拉取标记并重试

**文档**

- 重写 README：快速开始改为网页配置流程

### v1.1.0（2026-07-13）

- 新增数据源 DS-6：糯米是个背包
- 任务日志脱敏、进度条适配 6 数据源、`state.json` 并发写入加锁

### v1.0.0（2026-07-13）

- 首个正式版本：五数据源同步、Web 控制台、三类抽奖参与、LLM 解析、多用户隔离、pytest 测试套件

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

图表由仓库内静态 SVG 展示；GitHub Actions 会在有新 Star 时自动更新（见 `.github/workflows/star-history.yml`）。
