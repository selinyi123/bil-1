# Adapter: Cursor

Cursor discovers project skills under `.cursor/skills/<name>/SKILL.md`
(Agent Skills–compatible frontmatter).

## Recommended: directory junction (no content fork)

From the **repository root** (PowerShell):

```powershell
New-Item -ItemType Directory -Force -Path .cursor\skills | Out-Null
if (Test-Path .cursor\skills\binggo-mcp) { Remove-Item .cursor\skills\binggo-mcp -Recurse -Force }
cmd /c mklink /J ".cursor\skills\binggo-mcp" "mcp\skills\binggo-mcp"
```

Or copy (must re-copy after skill edits):

```powershell
New-Item -ItemType Directory -Force -Path .cursor\skills | Out-Null
Copy-Item -Recurse -Force mcp\skills\binggo-mcp .cursor\skills\binggo-mcp
```

## Personal (all projects) — global

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.cursor\skills" | Out-Null
$src = "D:\Code_list\Code_Python\bilibili_binggo\mcp\skills\binggo-mcp"
$dst = "$env:USERPROFILE\.cursor\skills\binggo-mcp"
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
cmd /c mklink /J "$dst" "$src"
```

本机已按上式做成 junction（改 `mcp/skills/binggo-mcp` 即全局生效）。

## Also required

- MCP `binggo` in `%USERPROFILE%\.cursor\mcp.json` (see `mcp/README.md`)
- Dashboard on `127.0.0.1:8787`

## Notes

- Prefer **project** skill via junction so SSOT stays under `mcp/skills/`.
- Do not put skills in `~/.cursor/skills-cursor/` (Cursor built-ins).
