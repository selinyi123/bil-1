# 方向四：API 层（稳定后端契约）— 拍板记录与设计想法

> 状态：**已拍板**；落地实现规范见 [04-api-contract-impl.md](./04-api-contract-impl.md)  
> 关联：[全栈路线图 §4](../fullstack-roadmap.md)、[方向一](./01-sqlite-data-layer.md)、[方向三](./03-backend-task-model.md)、[方向二](./02-realtime-progress.md)  
> 更新：2026-07-19

本文记录两件事：

1. **拍板结论**（产品/工程边界，已定）  
2. **设计想法**（对照现有 `web/app.py` + `app.js` 的取舍，供实现时对照）

---

## 0. 总前提（已对齐）

| 前提 | 含义 |
|------|------|
| 本地单机控制台 | 浏览器 ↔ 本机 FastAPI；**不上**公网多租户 / OAuth / API Gateway |
| 底座已稳 | 方向一 DB、方向三 Job、方向二 SSE 已落地；本方向**不改**任务语义与调度 B1 |
| 行为可感知不倒退 | 控制台现有按钮/筛选/任务/调度/设置路径，用户可感知行为不倒退 |
| 契约服务于多客户端 | 同一套 REST（+ 已有 SSE）可供控制台、未来 MCP/其它本地客户端复用 |
| 密钥不进响应 | Cookie / LLM Key 等仍不得出现在 JSON / SSE / OpenAPI 示例的明文里 |

---

## 1. 拍板结论一览（已定）

| 编号 | 议题 | 结论 | 说明 |
|------|------|------|------|
| **A** | URL 版本策略 | **A2** | 路径继续 `/api/...`；契约代用 OpenAPI `info` + 响应头 `X-Api-Contract` |
| **B** | 错误体 | **B2** | `{ error: { code, message, detail? } }`；过渡期双写顶层 `detail` |
| **C** | 成功响应信封 | **C1** | 不加全局 `{data}` 壳 |
| **D** | 正式契约范围 | **D2** | Stable / Streaming / Internal 分级 |
| **E** | Pydantic 覆盖 | **E2** | 请求全覆盖 + 关键响应模型 |
| **F** | 写操作幂等 | **F1** | v1 不做 Idempotency-Key |
| **G** | 与 Job/SSE | **G1** | 冻结方向二/三既有形状 |
| **H** | 与方向十 MCP | **H2** | 导出错误码表 + Job action 枚举；MCP 复用同一 REST |
| **I** | 前端兼容 | **I2** | 后端双写；`fetchJSON` 双读；toast 认 `error.code` |
| **J** | HTTP 方法清理 | **J1** | 以现前端实际动词为权威；未用动词标 alias/deprecated |

### 边角（已定）

| 编号 | 议题 | 结论 |
|------|------|------|
| **①** | Pydantic 校验 | 统一映射为 **HTTP 400** + `VALIDATION_ERROR`（不对外暴露 422） |
| **②** | `POST /api/jobs` 成功体 | 保持 `{ok, job}` |
| **③** | Job 历史 API | **v1 不做** |
| **④** | 契约代响应头 | **要**：所有 JSON API 响应带 `X-Api-Contract: 1` |
| **⑤** | 内部异常文案 | 用户友好句进 `message`；堆栈只进日志 |

---

## 2. 状态

| 项 | 状态 |
|----|------|
| 总前提 | ✅ 已定 |
| 拍板 A–J | ✅ 全部按建议 |
| 边角 ①–⑤ | ✅ 已定 |
| 落地实现规范 | ✅ [04-api-contract-impl.md](./04-api-contract-impl.md) |
| 编码 | ✅ 已落地 |

讨论记录：

| 日期 | 内容 |
|------|------|
| 2026-07-18 | 初稿：给出 A–J 建议供拍板 |
| 2026-07-19 | 用户确认：**全部按建议**；落地实现规范成文 |
