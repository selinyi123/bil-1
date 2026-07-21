# Adapter: OpenAI Codex

Codex-compatible agents that support Agent Skills typically load a skill
directory containing `SKILL.md` (see Codex / agent skills docs for the active
search path—often a project `.agents/skills` or user skills directory).

## Project install

**Windows**

```powershell
New-Item -ItemType Directory -Force -Path .agents\skills | Out-Null
if (Test-Path .agents\skills\binggo-mcp) { Remove-Item .agents\skills\binggo-mcp -Recurse -Force }
cmd /c mklink /J ".agents\skills\binggo-mcp" "mcp\skills\binggo-mcp"
```

**macOS / Linux**

```bash
mkdir -p .agents/skills
ln -sfn ../../mcp/skills/binggo-mcp .agents/skills/binggo-mcp
```

If your Codex build only reads `SKILL.md` from a configured path, point that
path at `mcp/skills/binggo-mcp`.

## Also required

- MCP: stdio `python -m binggo_mcp` with `cwd` = repo root and `PYTHONPATH=mcp`
  (or editable install)—same as `mcp/README.md`
- Dashboard on `127.0.0.1:8787`
