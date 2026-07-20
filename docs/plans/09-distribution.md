# 方向九：分发与安装 — 拍板记录与设计想法

> 状态：**已拍板**；落地实现规范见 [09-distribution-impl.md](./09-distribution-impl.md)  
> 关联：[全栈路线图 §9](../fullstack-roadmap.md)、[方向七 可观测性](./07-observability.md)、[方向八 配置与安全](./08-config-security.md)、[Windows 打包说明](../../packaging/windows/README.md)  
> 更新：2026-07-20

本文记录两件事：

1. **拍板结论**（产品/工程边界，已定）  
2. **设计想法**（对照现有 PyInstaller / Inno / Release CI / 启动器 / 关于页的取舍）

---

## 0. 总前提（已对齐）

| 前提 | 含义 |
|------|------|
| 分发链路已可用 | Windows Setup + Portable + `release-windows.yml` **已能发版**；本方向是体验与工程化补强，**不推倒 Windows 流水线** |
| Windows 双产物保留 | 安装包（Inno）与便携包（zip）继续并存 |
| 新增 macOS 产物 | 用户需求：提供可在苹果电脑运行的程序包（见拍板 **K**） |
| 数据与卸载策略 | Windows 安装版 `%APPDATA%\Binggo` 卸载不删；macOS 默认 `~/Library/Application Support/Binggo`；便携均支持 `BINGGO_PORTABLE=1` |
| 诊断底座已有 | 方向七诊断包 + 方向八 `/api/runtime`；本方向**复用**，不上崩溃云上报 |
| 无应用商店 / 无静默强更 | 不进微软商店 / Mac App Store；不自动覆盖用户未确认的安装 |
| 业务功能不改 | 登录、任务、调度、LLM 等可感知行为不变 |

---

## 1. 现状摘要（拍板依据）

（略；详见初稿讨论。要点：版本多处手写、UI 无 Version、无检查更新、仅 Windows 打包。）

---

## 2. 拍板结论一览（已定）

| 编号 | 议题 | 结论 | 说明 |
|------|------|------|------|
| **A** | 版本单一来源（SSOT） | **A1** | `__version__` 权威；构建/iss/FastAPI 从此注入或读取 |
| **B** | 应用内检查更新 | **B2** | 手动「检查更新」：读 GitHub Releases，有新版则提示并打开下载页 |
| **C** | UI 版本可见性 | **C1** | 概览关于区展示 Version + 检查更新 / 打开 Releases |
| **D** | 崩溃 / 安装失败诊断 | **D1** | 复用诊断包 + 启动器失败文案指向日志；不上报 |
| **E** | 升级 UX | **E1** | 提示下载；用户自行安装/换包 |
| **F** | Inno 语言 | **F2** | 尽力加简体中文；无 isl 则英文 + 文档 |
| **G** | 代码签名 | **G1** | v1 **不做**商业证书 / Apple 公证（Notarization） |
| **H** | 与方向七/八 | **H1** | 版本进 runtime/诊断；路径策略按平台扩展（见 K） |
| **I** | 测试范围 | **I1** | pytest 覆盖版本比较/更新解析/路径；完整装包在 release CI |
| **J** | UI/API 幅度 | **J1** | 最小：Version + 检查更新 |
| **K** | macOS 部署 | **K1** | 提供 macOS **Apple Silicon (arm64)** `.app` + zip；数据目录走 Application Support；CI 增加 macos 构建任务 |

### 边角（已定）

| 编号 | 议题 | 结论 |
|------|------|------|
| **①** | Releases 仓库 | `luovicter-collab/bilibinggo` |
| **②** | 版本比较 | semver `MAJOR.MINOR.PATCH`；忽略 `v` 前缀 |
| **③** | 检查更新网络 | GitHub API；短超时；失败不阻断 |
| **④** | 多平台更新文案 | 按 `sys.platform` / runtime 提示下载 Windows Setup/Portable 或 macOS zip |
| **⑤** | README changelog | 叙述可手写；版本数字以 `__version__` 为准 |
| **⑥** | 分期 | P1 SSOT+UI → P2 检查更新 → P3 启动器/Inno 中文 → **P4 macOS 打包与 CI** |
| **⑦** | macOS Intel | v1 **不强制**单独 x86_64 产物；文档说明 Intel Mac 可用源码运行或 Rosetta（若仅提供 arm64 则写明「需 Apple Silicon」） |
| **⑧** | Gatekeeper | 未公证时文档写清「右键 → 打开」；不做付费 Developer ID |

---

## 3–8.（设计展开与非目标）

核心取舍仍以「建议稿」为准；**增量**为拍板 **K1**：在不大改业务代码前提下，用 PyInstaller 产出 macOS `.app`，并修正 `user_home()` 在 Darwin frozen 下的默认路径。

**非目标补充：** Mac App Store、强制 Notarization、Windows/macOS 自动静默安装、Linux 安装包（可另议）。

---

## 9. 状态

| 项 | 状态 |
|----|------|
| 总前提 | ✅ 已定 |
| 拍板 A–J / 边角 | ✅ 全部按建议 |
| 拍板 **K** macOS | ✅ K1（用户追加） |
| 落地实现规范 | ✅ [09-distribution-impl.md](./09-distribution-impl.md) |
| 编码 | ⏳ 未开始 |

讨论记录：

| 日期 | 内容 |
|------|------|
| 2026-07-20 | 初稿：A–J 与边角建议供拍板 |
| 2026-07-20 | 用户确认：**按建议**；追加 **macOS 部署**；落地规范成文 |
