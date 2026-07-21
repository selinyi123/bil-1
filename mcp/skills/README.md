# Binggo skills (extension)

Canonical skill follows the **[Agent Skills](https://agentskills.io/specification)** open
format (`SKILL.md` + progressive `references/`). It teaches agents how to use the
**local** `binggo` MCP. It does **not** change Binggo application code under `src/` / `web/`.

```text
mcp/skills/
  README.md
  binggo-mcp/                 ← SSOT v0.2（agentskills.io）
    SKILL.md                  ← 决策树 / 硬规则 / 登录 / gotchas / 速查
    references/
      tools.md                ← 全工具参数
      workflows.md            ← W1–W13 清单式流程
      troubleshooting.md      ← 排障
      examples.md             ← 对话→工具序列示例
  adapters/                   ← Cursor / Claude / Codex / generic
```

借鉴开源优质 Skill（如 anthropics/skills 的 docx、webapp-testing）：**触发清晰的 description**、**决策树**、**gotchas**、**清单式工作流**、**examples**，并用 progressive disclosure 把长表放进 `references/`。

## Design rules applied

| Rule | How we follow it |
|------|------------------|
| Open `SKILL.md` frontmatter | `name` + `description` (+ license / compatibility / metadata) |
| `name` = folder name | `binggo-mcp` |
| Description = WHAT + WHEN | Third person, trigger keywords, explicit non-goals |
| Progressive disclosure | Lean `SKILL.md`; details in `references/` |
| Concise | No Tailscale/remote; no app implementation tutorials |
| Extension only | Lives under `mcp/`; never patches business logic |

## Install / attach by agent

See [adapters/README.md](adapters/README.md).

Quick links:

- [Cursor](adapters/cursor.md)
- [Claude Code](adapters/claude-code.md)
- [OpenAI Codex](adapters/codex.md)
- [Continue / Windsurf / generic](adapters/generic.md)

## Pairing with MCP

1. Configure MCP (`mcp/README.md`)
2. Attach this skill via an adapter
3. Keep dashboard on `127.0.0.1:8787`
