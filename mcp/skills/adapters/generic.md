# Adapter: generic (Continue, Windsurf, Copilot Chat, custom agents)

Any agent that implements **[Agent Skills](https://agentskills.io/specification)**
can use the SSOT folder:

```text
mcp/skills/binggo-mcp/
├── SKILL.md
└── references/
```

## Checklist

1. **Discover** — Ensure the product indexes `name` + `description` from `SKILL.md`
2. **Path** — Add `mcp/skills/binggo-mcp` to that product’s skills path, **or**
   symlink/copy into its expected directory (examples: `.continue/skills`,
   Windsurf skills folder, VS Code Copilot skill path—follow that product’s docs)
3. **MCP** — Configure stdio server `binggo` exactly as in `mcp/README.md`
4. **Runtime** — Dashboard must listen on `http://127.0.0.1:8787`

## If the product is not Agent Skills–compatible

Paste or `@`-attach `mcp/skills/binggo-mcp/SKILL.md` (and open
`references/workflows.md` when needed) as manual instructions. Behavior is the
same; only discovery differs.

## Do not

- Fork conflicting copies of workflows per agent
- Add remote/Tailscale instructions into the skill body
- Modify Binggo `src/` / `web/` for skill support
