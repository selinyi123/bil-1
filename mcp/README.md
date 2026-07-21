# Binggo MCP（私人本地扩展）

将本机已运行的 Binggo 控制台能力，通过 **MCP stdio** 暴露给任意 Agent。  
**不修改**主项目 `src/` / `web/` 业务代码；只 HTTP 调用 `http://127.0.0.1:8787`。

规范见仓库：`docs/plans/10-mcp.md`、`docs/plans/10-mcp-impl.md`。

## 前置

1. 控制台已启动且监听 **8787**（开发：`python scripts/run_dashboard.py`）
2. 安装本扩展依赖（任选其一）：

```bash
pip install -r mcp/requirements.txt
# 或
pip install -e mcp/
```

## 启动

在仓库根目录：

```bash
python -m binggo_mcp
```

若未 `pip install -e mcp/`，需把 `mcp` 目录加入 `PYTHONPATH`：

```bash
# Windows PowerShell
$env:PYTHONPATH = "mcp"
python -m binggo_mcp
```

## 挂到任意 MCP 客户端（通用示例）

与能正常识别的 stdio 服务对齐时，**务必带 `"type": "stdio"`**（Cursor 等客户端把它当必填；缺了可能直接不加载）。

推荐（绝对路径，少踩 PATH / 相对路径坑）：

```json
{
  "mcpServers": {
    "binggo": {
      "type": "stdio",
      "command": "C:/Users/15745/miniconda3/python.exe",
      "args": ["-m", "binggo_mcp"],
      "cwd": "D:/Code_list/Code_Python/bilibili_binggo",
      "env": {
        "PYTHONPATH": "D:/Code_list/Code_Python/bilibili_binggo/mcp"
      }
    }
  }
}
```

说明：

| 项 | 注意 |
|----|------|
| `type` | 写成 `"stdio"`，与 `codegraph` 一致 |
| `command` | 用**绝对路径**的 python（Agent 启动时 PATH 往往不是你终端里的 conda） |
| `PYTHONPATH` | 用 `.../mcp` 的**绝对路径**；`"mcp"` 相对路径在部分客户端会解析失败 |
| 已 `pip install -e mcp/` | 可去掉 `env.PYTHONPATH`，但仍建议绝对路径 python |

改完后：打开客户端的 MCP / Tools 面板看 `binggo` 是否变绿；Cursor 可 **Reload Window** 或开关一次该 MCP。

若仍失败，在终端手动跑同一条命令排查：

```powershell
cd D:\Code_list\Code_Python\bilibili_binggo
$env:PYTHONPATH = "D:\Code_list\Code_Python\bilibili_binggo\mcp"
C:\Users\15745\miniconda3\python.exe -m binggo_mcp
```

应挂起等待输入（stdio 正常）；若立刻 `ModuleNotFoundError`，说明包路径仍不对。

## Agent 说明

| 规则 | 说明 |
|------|------|
| 基址 | 固定 `http://127.0.0.1:8787` |
| 串行 | 全部 tool 同一进程内全局锁，不能并发 |
| Job | 除登录外，启动后等到终态再返回 |
| 登录 | `account_login` 在二维码就绪后返回 **PNG 图片**；再用 `job_get` 看是否成功 |
| 取消 | 仅 `account_login_cancel`（关扫码）；无通用取消任务 |
| 密钥 | 不回传 Cookie / 明文 API Key |
| MCP instructions | `binggo_mcp/instructions.py` + 各 tool docstring |
| Skill（本机 Agent） | 开放格式 SSOT：[`skills/binggo-mcp/`](skills/binggo-mcp/)；多 Agent 挂载见 [`skills/adapters/`](skills/adapters/) |

## 工具一览

见 `docs/plans/10-mcp-impl.md` §2。重载 MCP 后可读到 instructions；挂上 Skill 后 Agent 按场景编排调用。
