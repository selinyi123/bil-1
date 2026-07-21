# Skill adapters (multi-agent)

**Source of truth:** [`../binggo-mcp/`](../binggo-mcp/) — Agent Skills open format.

Adapters do **not** fork the workflow content. They only document where each
product expects skills to live, and how to point at the SSOT (copy, symlink, or
vendor path).

| Product | Adapter |
|---------|---------|
| Cursor | [cursor.md](cursor.md) |
| Claude Code | [claude-code.md](claude-code.md) |
| OpenAI Codex | [codex.md](codex.md) |
| Continue, Windsurf, Copilot, others | [generic.md](generic.md) |

## Update policy

Edit only `mcp/skills/binggo-mcp/`. Re-run the adapter’s “sync” step if you used
a copy instead of a link.
