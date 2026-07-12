# Star History 图表

README 中的 Star 趋势图使用仓库内的静态 SVG：

- `assets/star-history/star-history-light.svg`
- `assets/star-history/star-history-dark.svg`

推送后 GitHub 会按深浅色主题自动切换显示。

## 自动更新

`.github/workflows/star-history.yml` 每 6 小时运行一次，并在有新 Star 时更新图表与 README 嵌入块。

若 Actions 因 Token 权限失败，可手动在 GitHub 仓库 **Actions → Star History → Run workflow** 重试。自有仓库通常使用内置 `GITHUB_TOKEN` 即可。

## 手动触发

仓库页面 → **Actions** → **Star History** → **Run workflow**
