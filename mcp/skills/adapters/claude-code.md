# Adapter: Claude Code

Claude Code loads Agent Skills from project or user skill directories
(see current Claude Code docs for exact paths; commonly `.claude/skills/` or
plugin/skill install paths).

## Project install (symlink / junction)

From repository root:

**Windows**

```powershell
New-Item -ItemType Directory -Force -Path .claude\skills | Out-Null
if (Test-Path .claude\skills\binggo-mcp) { Remove-Item .claude\skills\binggo-mcp -Recurse -Force }
cmd /c mklink /J ".claude\skills\binggo-mcp" "mcp\skills\binggo-mcp"
```

**macOS / Linux**

```bash
mkdir -p .claude/skills
ln -sfn ../../mcp/skills/binggo-mcp .claude/skills/binggo-mcp
```

## Alternative

```bash
npx skills add ./mcp/skills/binggo-mcp
```

(Use the Skills CLI if your Claude Code setup uses skills.sh / `npx skills`.)

## Also required

- Register the `binggo` MCP stdio server in Claude Code MCP settings
- Local dashboard at `http://127.0.0.1:8787`
