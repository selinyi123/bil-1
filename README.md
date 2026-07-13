# bilibili_binggo (Binggo)

聚合 B 站抽奖 UP 合集，增量发现活动、本地管理参与状态，Web 控制台一键参与互动 / 转发 / 预约抽奖。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 Cookie（扫码登录，推荐）
cp config/cookies.txt.example config/cookies.txt
python scripts/bili_login.py

# 3. 配置 LLM（转发抽奖解析，推荐）
cp config/llm.env.example config/llm.env
# 编辑 config/llm.env，填入你的 API Key（见下方说明）

# 4. 释放 8787 端口（若启动时报「端口已被占用」）
# Windows PowerShell：
netstat -ano | findstr ":8787"
Stop-Process -Id <PID> -Force   # 将 <PID> 换为上一行 LISTENING 对应的进程号

# 5. 启动本地控制台
python scripts/run_dashboard.py
```

浏览器打开 http://127.0.0.1:8787

### LLM 是做什么的？

在「一键更新活动链接」拉取详情时：

- **互动抽奖 / 预约抽奖**：走 B 站官方接口，**不消耗 LLM**
- **转发抽奖**：没有官方结构化字段，会调用大模型阅读动态正文，抽取奖品、开奖时间、参与条件、中奖人数等

因此只需配置一个**便宜的文本生成模型**即可，不需要视觉或多模态能力。

**推荐使用 [DeepSeek-V4-Flash](https://www.deepseek.com/)**（速度快、成本低，适合 JSON 结构化抽取）。

编辑 `config/llm.env`：

```env
LLM_API_KEY=你的_API_Key
LLM_BASE_URL=你的_BASE_URL
LLM_MODEL_NAME=DeepSeek-V4-Flash
```

| 字段 | 说明 |
|------|------|
| `LLM_API_KEY` | 服务商提供的密钥（**勿提交 Git**） |
| `LLM_BASE_URL` | OpenAI 兼容接口地址，按你购买的服务修改 |
| `LLM_MODEL_NAME` | 模型名称，建议 `DeepSeek-V4-Flash` 或同档低价文本模型 |

未配置 LLM 时，转发抽奖的活动会缺少奖品/开奖时间等字段，但互动与预约类活动不受影响。

## 更新日志

### v1.0.0（2026-07-13）

首个正式版本，面向本地个人使用的 B 站抽奖活动管理工具。

**核心能力**

- **五数据源增量同步**：并行检查 DS-1～DS-5 合集，仅处理新增活动链接
- **活动流水线**：合并去重 → 类型分类（转发 / 预约 / 互动）→ 详情拉取 → 状态刷新
- **增量更新**：无新链接时秒级完成；有新链接或待补拉记录时，只处理缺失项
- **Web 控制台**：扫码登录、一键更新、活动列表（筛选 / 排序 / 分页）、单行参与、任务进度与日志
- **三类抽奖参与**：互动 / 转发（点赞→关注→收藏→转发→评论）、预约（一键预约）
- **转发抽奖 LLM 解析**：配置 OpenAI 兼容接口，自动抽取奖品、开奖时间、参与条件
- **多用户隔离**：活动数据全局共用，参与状态按 B 站 UID 分目录存储
- **CLI 全链路**：数据源检查、合并、分类、拉取详情、参与、热度补全等脚本

**界面与体验**

- 概览 / 数据源 / 活动三页布局，侧边栏可收起
- 夜间模式，一键更新浮动进度卡片
- LLM 配置面板与连接测试，参与评论文案可自定义

**稳定性与安全**

- JSON 数据原子写入，降低中断导致文件损坏的风险
- API 输入校验（活动 ID 格式、任务白名单、LLM 地址 scheme）
- 单条分类 / 拉取失败不阻断整批任务，失败项下次更新自动重试
- 日志与错误信息脱敏，Cookie / LLM Key 不入库
- 本地绑定 `127.0.0.1:8787`，不对外暴露服务

**测试**

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

## 功能概览

- **数据源**：五个 UP 合集增量检查，仅处理新增链接
- **活动信息**：合并、分类、拉取详情，**历史记录全部保留**（不删除过期活动）
- **参与活动**：互动/转发类五步（点赞→关注→收藏→转发→评论），预约类一键预约
- **多用户**：活动信息共用，参与状态按 B 站 UID 分目录存储（`data/users/{uid}/`）

## 配置

| 文件 | 说明 |
|------|------|
| `config/cookies.txt` | B 站登录 Cookie（**勿提交 Git**） |
| `config/cookies.txt.example` | Cookie 文件模板 |
| `config/llm.env` | 转发抽奖 LLM 解析配置（**勿提交 Git**） |
| `config/llm.env.example` | LLM 配置模板 |

```bash
cp config/cookies.txt.example config/cookies.txt
cp config/llm.env.example config/llm.env
```

## 目录结构

```
bilibili_binggo/
├── config/          # 本地配置（敏感信息）
├── data/            # 本地数据（默认不提交 Git）
│   ├── output/      # 活动信息（共用）
│   ├── cache/       # 解析缓存
│   └── users/       # 按 UID 隔离的参与状态
├── docs/            # 文档
├── scripts/         # CLI 入口
├── src/             # 核心逻辑
└── web/             # 本地控制台
```

## CLI

各数据源检查、合并、分类、拉取详情、参与等命令见 [docs/cli.md](docs/cli.md)。

## 开源与隐私

- 代码中路径均相对项目根目录，无硬编码绝对路径
- `config/cookies.txt`、`config/llm.env`、`data/` 已加入 `.gitignore`
- 推送前请确认未包含个人 Cookie 与参与记录

## 许可

MIT（可按需调整）

## Star History

<!-- star-history:start -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/star-history/star-history-dark.svg">
  <img alt="Star history" src="assets/star-history/star-history-light.svg">
</picture>
<!-- star-history:end -->

图表由仓库内静态 SVG 展示；GitHub Actions 会在有新 Star 时自动更新（见 `.github/workflows/star-history.yml`）。
