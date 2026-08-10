<p align="center">
  <img src="docs/images/logo.svg" alt="Binggo" width="80" height="80">
</p>

<h1 align="center">Binggo · bil-1 数字人格抽奖运营系统（DPMS）</h1>

<p align="center">
  <strong>本机 B 站抽奖助手</strong> —— 自动发现抽奖活动、一键/三连自动参与、定时调度、中奖深检推送
</p>

<p align="center">
  Python 3.12 · FastAPI · SQLite · Vite + TypeScript ·
  <em>Local-first：数据只在本机，仅监听 127.0.0.1</em>
</p>

---

## 项目简介

**Binggo** 是 bil-1 数字人格抽奖运营系统（DPMS）的核心组件：一个本地运行的 B 站抽奖自动化工具。围绕「**发现 → 筛选 → 参与 → 跟踪 → 中奖检测**」闭环设计，全程在本机完成，无需第三方服务器。

- 自动扫描 UP 合集 / 话题 / 手动清单 / 外部 API / 监控用户转发，增量入库
- Web 控制台浏览、筛选、统计活动，点击按钮即可参与
- 定时调度器到点自动执行更新与参与，撞车即停、失败自动降级
- 中奖深检（@/回复/私信 + 关键词）命中后通过 15 种渠道推送提醒

## 功能特性

### 抽奖发现
| 数据源 | 说明 |
| --- | --- |
| DS-1~7 | 内置 UP 合集（视频简介 / 专栏 / Opus 动态帖），增量检查点 |
| DS-8 手动清单 | `config/manual_dyids.txt`，每行一个动态 ID/链接 |
| DS-9 话题源 | `config/topic_tags.txt`，按话题名抓取热门/历史动态 |
| DS-10 外部 API | `config/api_sources.txt`，远程 JSON 或 `file://` 本地清单 |
| WATCH 监控 | 监控用户转发动态窗口同步，补合集漏网 |

### 自动参与
- **五连参与**：点赞 → 关注 → 收藏 → 转发 → 评论；**预约抽奖**两步（关注 + 预约）
- **转发抽奖增强**：LLM 结构化解析正文（奖品/开奖时间/条件）、评论验证码 OCR、抄热评、@好友带话题、目标乱序 + 随机延迟、充电抽奖自动跳过
- **参与文案**：自定义固定文案 / 随机借用评论区热评（可剔除作者与屏蔽词）

### 账号与网络
- **多账号池**：扫码登录自动登记，Web 界面一键切换，参与记录按 uid 隔离
- **代理**：`BINGGO_PROXY` 环境变量或 `config/proxy.json`，客户端与登录均走代理
- **风控友好**：WBI 签名、请求限流（令牌桶）、指数退避重试、Line 多线路容灾、单条失败降级不阻塞整批

### 定时与通知
- **定时调度**：整点刷新批次（一键更新→监控扫描→状态刷新）、非刷新小时每 5 分钟三连参与；时间槽可视化展示
- **中奖深检**：扫描 @我 / 回复 / 私信，关键词判定（支持 `~` 黑名单），私信命中后标记已读，避免重复提醒
- **15 渠道推送**：Server酱 / Bark / PushDeer / Telegram / 钉钉 / 企业微信（应用+机器人）/ iGot / PushPlus / Qmsg / 邮件 / Gotify / 飞书 / 酷推 / Server酱(旧)

### 治理与安全
- **关注分区**：参与后自动移入「抽奖临时关注」分区，清理时按分区批量取关
- **清理**：删除超期转发动态 + 取关（白名单保护、预演模式），原创动态绝不误删
- **本地安全**：仅绑定回环地址、Cookie/活动库/参与记录全在本机、日志与诊断包脱敏、凭据不回显

## 快速开始

### 源码运行（开发模式）

```bash
python -m pip install -r requirements.txt
python scripts/run_dashboard.py        # 或 python binggo_launcher.py
# 浏览器打开 http://127.0.0.1:8787
```

首次使用：控制台「登录」扫码 → 配置 LLM（转发抽奖解析用）→ 一键更新拉取活动 → 参与 / 开启定时调度。

### 打包安装

| 平台 | 方式 |
| --- | --- |
| Windows | `packaging/windows/build.ps1`（PyInstaller onedir + Inno Setup 安装包） |
| macOS | `packaging/macos/build.py`（dmg/zip） |

打包版数据位于 `%APPDATA%\Binggo`（Windows）或 `~/Library/Application Support/Binggo`（macOS），程序目录内不含用户数据，可放心升级替换。

## 配置说明

所有配置集中在 `config/`（模板以 `*.example` 提供，首次启动自动复制）：

| 文件 | 用途 |
| --- | --- |
| `cookies.txt` | 登录凭据（扫码登录自动写入，**请勿提交**） |
| `sources.yaml` | 数据源注册表（DS-1~10） |
| `participate_enhance.json` | 参与增强：抄热评 / @好友 / 话题 / 乱序 / 随机延迟 / 分区 |
| `notify.json` | 15 渠道推送凭据 + 中奖关键词 |
| `manual_dyids.txt` / `topic_tags.txt` / `api_sources.txt` | DS-8 / DS-9 / DS-10 数据源清单 |
| `llm.env` | LLM 凭据（OpenAI 兼容，仅转发抽奖解析消耗） |

常用环境变量：`BILI_COOKIE`（临时 Cookie）、`BILI_RPS`（请求速率）、`BINGGO_PROXY`（代理 URL）、`BINGGO_CAPTCHA_OCR_URL`（评论验证码 OCR 服务）、`BINGGO_HOME`（自定义数据目录）。

## 项目结构

```
├── binggo_launcher.py        # 桌面启动器（单实例、拉起服务、开浏览器）
├── src/                      # 领域层（不依赖 Web）
│   ├── bilibili_client.py    # B 站 API 客户端（WBI 签名/限流/重试）
│   ├── bilibili_login.py     # 扫码登录
│   ├── lottery_*.py          # 分类/解析/补全/开奖时间/参与/动作
│   ├── notify.py             # 15 渠道推送
│   ├── draw_check.py         # 中奖深检
│   ├── clear_follows.py      # 清理动态与取关
│   ├── account_pool.py       # 多账号池
│   ├── sources/              # DS-1~10 数据源
│   ├── pipeline/             # 发现流水线（分类→详情→状态→入库）
│   └── db/                   # SQLite 数据层（schema v2 + 迁移）
├── web/                      # FastAPI 控制台 + 前端
│   ├── app.py                # 全部 REST API + SSE
│   ├── actions.py            # 任务动作执行器（login/refresh/participate/…）
│   ├── job_runner.py         # 任务状态机（互斥/持久化/取消）
│   ├── auto_scheduler.py     # 定时调度器（时间槽）
│   └── frontend/             # Vite + TS 前端（无框架原生 DOM）
├── mcp/                      # MCP stdio 扩展（只调用本地 API）
├── scripts/                  # 运维/迁移/调试脚本
└── tests/                    # pytest 套件（约 470 项）
```

## 开发与测试

```bash
python -m pytest tests              # 后端测试（mock，可离线）
cd web/frontend
npm run typecheck                   # 前端类型检查（strict）
npm run test                        # 前端单测（vitest）
npm run build                       # 构建前端到 web/static/dist
```

## 文档

- `docs/fullstack-roadmap.md` — 全栈演进路线（10 个方向）
- `docs/pipeline-redesign.md` — 发现流水线设计
- `docs/plans/` — 各方向拍板与实现规范
- `DESIGN.md` — （注：仓库内为遗留的第三方设计资产，与本项目无关）

## 许可证

[MIT](LICENSE)
