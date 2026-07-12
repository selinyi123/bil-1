# 快速开始

本指南帮助你在本地运行 Binggo，并完成首次登录与活动更新。

## 环境要求

- Python 3.10+
- 可访问 B 站 API 的网络环境

## 1. 克隆与安装

```bash
git clone <your-repo-url> bilibili_binggo
cd bilibili_binggo
pip install -r requirements.txt
```

## 2. 配置敏感文件

```bash
cp config/cookies.txt.example config/cookies.txt
cp config/llm.env.example config/llm.env
```

- `config/cookies.txt`：B 站登录凭证，**切勿提交到 Git**
- `config/llm.env`：转发抽奖正文解析用的 LLM API Key，**切勿提交到 Git**

## 3. 登录 B 站账号

```bash
python scripts/bili_login.py
```

用手机哔哩哔哩 App 扫描终端二维码（或打开 `data/login_qrcode.png`），确认后 Cookie 自动写入 `config/cookies.txt`。

## 4. 启动 Web 控制台

```bash
python scripts/run_dashboard.py
```

访问 http://127.0.0.1:8787

### 控制台功能

| 页面 | 说明 |
|------|------|
| 概览 | 活动统计、快捷更新 |
| 账号 | 扫码登录、查看关注/动态等 |
| 数据源 | 五个 UP 合集的检查状态 |
| 活动 | 可参与或已参加的活动列表 |
| 日志 | 后台任务执行记录 |

## 5. 一键更新活动

在控制台点击 **一键更新活动链接**，流程为：

1. 检查 DS-1 ~ DS-5 是否有新专栏
2. 合并去重（保留全部历史链接）
3. 仅对新链接分类
4. 仅对新活动拉取详情
5. 保存到 `data/output/enriched_latest.json`（**不删除过期活动**）

## 6. 参与活动

在活动列表点击 **参与**：

- **互动/转发抽奖**：点赞 → 关注 → 收藏 → 转发 → 评论
- **预约抽奖**：一键预约

参与状态保存在 `data/users/{你的UID}/participations.json`，不同账号互不影响。

## 推送 Git 前检查

```bash
git status
```

确认以下文件**不在**待提交列表中：

- `config/cookies.txt`
- `config/llm.env`
- `data/` 下所有运行时数据

## 常见问题

**Q: 提示未登录或 -352 风控？**  
A: 重新运行 `python scripts/bili_login.py` 扫码登录。

**Q: 活动列表为空？**  
A: 先执行一键更新；列表仅显示「可参与」或「已参加」的活动。

**Q: 换账号后参与状态不对？**  
A: 参与记录按 UID 隔离，换账号登录后会自动读取对应目录。
