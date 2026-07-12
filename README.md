# bilibili_binggo (Binggo)

聚合 B 站抽奖 UP 合集，增量发现活动、本地管理参与状态，Web 控制台一键参与互动 / 转发 / 预约抽奖。

[![Star History Chart](https://api.star-history.com/svg?repos=luovicter-collab/bilibinggo&type=Date)](https://star-history.com/#luovicter-collab/bilibinggo&Date)

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 Cookie（扫码登录，推荐）
python scripts/bili_login.py

# 3. 启动本地控制台
python scripts/run_dashboard.py
```

浏览器打开 http://127.0.0.1:8787

更详细的说明见 [docs/quickstart.md](docs/quickstart.md)。

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
