# 本地生成 Star History 图表（一次性）

若 GitHub Actions 尚未跑通，可在本机用 **Classic PAT（含 `public_repo` 权限）** 生成图表：

```powershell
$env:GITHUB_TOKEN = "你的_classic_pat_不要提交到_git"
npm ci --prefix .github/star-history-renderer --no-audit --no-fund 2>$null
# 或直接使用已推送的 workflow：在仓库 Actions 页手动 Run workflow
```

## 配置 GH_PAT 密钥（推荐）

1. 创建 **Classic Personal Access Token**，勾选 **`public_repo`**（不要用仅 Metadata 的 Fine-grained Token）
2. 在仓库 Settings → Secrets → Actions 添加 `GH_PAT`
3. 打开 Actions → **Star History** → **Run workflow**

Workflow 会自动生成 `assets/star-history/*.svg` 并更新 README 中的图表嵌入。

参考：[Star History Action](https://github.com/narayann7/star-history-action)
