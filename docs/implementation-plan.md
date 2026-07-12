# 功能实现方案文档

> 基于 [data-source-analysis.md](./data-source-analysis.md)  
> 范围：5 个固定数据源的**发现 → 链接提取 → 三基类归类 → 验证**  
> 日期：2026-07-12  
> 阶段：**方案设计**（本文档不包含可运行代码）

---

## 1. 项目目标

### 1.1 要做什么

构建一个 **抽奖活动发现流水线**，从 5 个指定 UP 主的内容中：

1. **发现**最新一期合集（视频简介 / 专栏 cv / Opus 帖）
2. **提取**其中指向他人抽奖活动的链接（归一为 `dynamic_id`）
3. **归类**为三种基类：`转发抽奖`、`预约抽奖`、`互动抽奖`
4. **验证**活动是否仍有效（未开奖、可参与）
5. 输出结构化候选列表，供后续「自动参与」模块消费

### 1.2 不做什么（本阶段）

- 不实现自动关注 / 转发 / 评论 / 预约
- 不做全站搜索、不扩展第 6 个数据源
- 不做 Web UI（可后续加）

### 1.3 成功标准

| 指标 | 目标 |
|------|------|
| 5 源均可自动拉取最新容器 | 100% |
| 活动链接提取准确率 | ≥ 95%（以人工抽检 50 条为准） |
| 三基类归类准确率 | ≥ 90%（结合 API 校正后） |
| 有效活动误杀率 | < 5% |
| 单次全量轮询耗时 | < 3 分钟（含限速） |

---

## 2. 系统架构

### 2.1 总体架构图

```text
┌─────────────────────────────────────────────────────────────────┐
│                        Scheduler（定时器）                        │
│                   建议间隔：10～30 分钟/次                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Fetcher DS-1   │ │ Fetcher DS-2~4  │ │  Fetcher DS-5   │
│  VideoList      │ │  ArticleList    │ │  OpusList       │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────────────────────────────┐
│ Parser Video    │ │ Parser Column (cv)                      │
│ DescParser      │ │  ├─ FanqieParser   (DS-2)               │
└────────┬────────┘ │  ├─ ToolmanParser  (DS-3)               │
         │          │  └─ JjunParser     (DS-4)               │
         │          └──────────────────┬──────────────────────┘
         │                             │
         │          ┌──────────────────▼──────────────────────┐
         │          │ Parser OpusPost (DS-5)                  │
         │          │  └─ HudongParser                        │
         │          └──────────────────┬──────────────────────┘
         │                             │
         └──────────────┬──────────────┘
                        ▼
              ┌───────────────────┐
              │  Normalizer       │  dynamic_id 归一 + 去重
              └─────────┬─────────┘
                        ▼
              ┌───────────────────┐
              │  Classifier       │  三基类 + API 校正
              └─────────┬─────────┘
                        ▼
              ┌───────────────────┐
              │  Validator        │  lottery_notice / detail
              └─────────┬─────────┘
                        ▼
              ┌───────────────────┐
              │  Storage + Export │  JSON/SQLite
              └───────────────────┘
```

### 2.2 模块职责

| 模块 | 职责 |
|------|------|
| **Fetcher** | 按 mid 拉取「最新未处理容器」元数据 |
| **Parser** | 针对数据源排版，提取 `(dynamic_id, lottery_type, metadata)` |
| **Normalizer** | t 链 → opus、去重、过滤容器自身 ID |
| **Classifier** | 合并 Parser 初判与 API 终判 |
| **Validator** | 过滤已开奖 / 已失效 / 非抽奖 |
| **Storage** | 持久化容器处理水位、活动候选、运行日志 |

### 2.3 技术栈建议

| 层次 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | 正则、HTTP、JSON 生态成熟 |
| HTTP | `httpx` 或 `requests` + 会话 Cookie | B 站接口风控 |
| HTML/JSON | `re` + `json` 或 `parsel` | INITIAL_STATE 解析 |
| 存储 | SQLite | 轻量，记录水位与候选 |
| 配置 | `config.yaml` | 5 源 mid、轮询间隔、Cookie 路径 |
| 日志 | `logging` 标准库 | 按数据源分 logger |

---

## 3. 数据源配置（固定）

```yaml
# config/sources.yaml（示意）
sources:
  - id: DS-1
    name: 哔哩抽奖小助理
    mid: 885439
    kind: video
    space_url: https://space.bilibili.com/885439/upload/video
    parser: video_desc
    poll:
      max_videos: 3          # 仅检查最近 3 期周报
      order: pubdate

  - id: DS-2
    name: 番茄薯条喵
    mid: 3546836235193146
    kind: cv
    space_url: https://space.bilibili.com/3546836235193146/upload/opus
    parser: fanqie
    poll:
      max_articles: 5

  - id: DS-3
    name: 你的抽奖工具人
    mid: 100680137
    kind: cv
    space_url: https://space.bilibili.com/100680137/upload/opus
    parser: toolman
    poll:
      max_articles: 8        # 日更多篇，略多抓
      title_priority:        # 优先处理这些标题关键词
        - 临期
        - 速看
        - 精选大奖
        - 史上最全

  - id: DS-4
    name: J君名
    mid: 126038161
    kind: cv
    space_url: https://space.bilibili.com/126038161/upload/opus
    parser: jjun
    poll:
      max_articles: 5

  - id: DS-5
    name: 互动抽奖娘
    mid: 3546776042736296
    kind: opus_post
    space_url: https://space.bilibili.com/3546776042736296/upload/opus
    parser: hudong
    poll:
      max_posts: 5
```

---

## 4. 发现层（Fetcher）详细设计

### 4.1 DS-1：视频列表

**流程**：

```text
space/arc/search(mid=885439, order=pubdate, ps=5)
  → 取 bvid 列表
  → 过滤标题含「抽奖周报」
  → 对比本地已处理 bvid 水位
  → 对未处理的 bvid 调 view 接口取 desc
```

**接口**：

```http
GET /x/space/arc/search?mid=885439&pn=1&ps=5&order=pubdate
GET /x/web-interface/view?bvid={bvid}
```

**水位键**：`processed_video:{bvid}`

**输出**：

```json
{
  "container_kind": "video",
  "container_id": "BV1Z6j76dEKC",
  "raw_content": "{desc 全文}",
  "published_at": 1783848700
}
```

### 4.2 DS-2/3/4：专栏列表

**流程**：

```text
x/article/metas?mid={mid}&sort=0&pn=1&ps={N}
  → 对比 cv 水位
  → GET read/cv{id} HTML
```

**接口**：

```http
GET /x/article/metas?mid={mid}&sort=0&pn=1&ps=8
GET https://www.bilibili.com/read/cv{cv_id}   # HTML
```

**水位键**：`processed_cv:{cv_id}`

**DS-3 优化**：同一日多篇高度重复，可配置「只处理标题含 临期|速看|精选 的 cv + 每日 1 篇史上最全」，降低冗余。

### 4.3 DS-5：Opus 帖列表

**难点**：`upload/opus` 列表**不一定**走 `article/metas`（互动抽奖娘的帖是 opus 动态）。

**推荐双通道**：

```text
通道 A（优先）:
  GET /x/polymer/web-dynamic/v1/feed/space?host_mid={mid}&offset=&page_size=20
  → 筛 type=opus / title 含「抽奖合集」
  → 取 opus id

通道 B（兜底）:
  article/metas 返回的 cv 若打开后跳转到 opus，则记录 opus_id
```

**水位键**：`processed_opus:{opus_id}`

**输出**：

```json
{
  "container_kind": "opus_post",
  "container_id": "1221421001768697897",
  "container_url": "https://www.bilibili.com/opus/1221421001768697897",
  "raw_content": "{HTML}",
  "published_at": 1783222643
}
```

### 4.4 通用 Fetch 要求

| 项 | 要求 |
|----|------|
| User-Agent | 完整浏览器 UA |
| Referer | `https://www.bilibili.com` |
| Cookie | 可选；无 Cookie 时部分接口 -352，需降级为纯 HTML 抓取 |
| 限速 | 每次请求间隔 ≥ 1s，遇 -509 指数退避 |
| 缓存 | 已抓 HTML 可落盘 `data/cache/{source}/{container_id}.html` 便于调试 |

---

## 5. 解析层（Parser）详细设计

### 5.1 公共基类 `BaseParser`

```python
class ParseResult(TypedDict):
    dynamic_id: str
    source_url: str
    lottery_type: Literal["转发抽奖", "预约抽奖", "互动抽奖"]
    raw_prize: str | None
    raw_lottery_time: str | None
    section: str | None
    link_text: str | None

class BaseParser(ABC):
    source_id: str

    @abstractmethod
    def parse(self, raw_content: str, container_meta: dict) -> list[ParseResult]: ...

    def extract_initial_state(self, html: str) -> dict | None: ...
    def extract_opus_nodes(self, state: dict) -> list[dict]: ...
```

**INITIAL_STATE 提取**（DS-2～5 共用）：

```regex
window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;
```

注意：非贪婪可能截断；实现时用「括号计数」或定位 `<script>` 更稳。

### 5.2 `VideoDescParser`（DS-1）

**输入**：视频 desc 纯文本  
**输出**：`lottery_type` 默认 `互动抽奖`

**核心逻辑**：

```python
PATTERN = re.compile(
    r"(?P<date>\d{2}月\d{2}日)\s+"
    r"(?P<url>https://t\.bilibili\.com/(?P<dynamic_id>\d{19}))"
    r"(?:奖品：(?P<prize>[^，\n]+))?"
    r"(?:，来自up主：(?P<sender>[^\s，\n]+))?"
)
```

**后处理**：

- `source_url = f"https://www.bilibili.com/opus/{dynamic_id}"`
- `raw_lottery_time`：由 `date` + 视频发布年推断完整日期（跨年需注意）

### 5.3 `FanqieParser`（DS-2 番茄薯条喵）

**策略**：**分区状态机 + INITIAL_STATE 节点顺序**

```text
状态 section = None
遍历正文节点（按文档顺序）:
  若文本匹配 ^#\s*(充电|预约|互动)抽奖 → 更新 section
  若文本匹配 ^#\s*(官方|非方?官方)抽奖 → 更新子 section
  若节点为 RICH_TEXT_NODE_TYPE_OPUS → 输出 (rid, map(section))
```

**section → lottery_type 映射**：

```python
SECTION_MAP = {
    "预约抽奖": "预约抽奖",
    "互动抽奖": "互动抽奖",
    "官方抽奖": "互动抽奖",
    "非官方抽奖": "转发抽奖",
    "非方官方抽奖": "转发抽奖",
    "充电抽奖": "互动抽奖",
}
```

**排除**：

- 文首「上期传送门」后第一个 opus
- 文本含 `本期完`

**兜底正则**（INITIAL_STATE 失败时）：

```regex
https?://(?:www\.)?bilibili\.com/opus/(\d{18,19})
```

### 5.4 `ToolmanParser`（DS-3 你的抽奖工具人）

**策略**：INITIAL_STATE 为主，箭头行正则辅助元数据

**分区识别**：

```regex
【置顶抽奖[①②③\d]*】  → section=置顶 → 转发抽奖
【\d{1,2}\.\d{1,2}日开奖部分】 → section=日期块 → 默认互动抽奖
```

**元数据正则**（可选）：

```regex
(?P<idx>\d+)、→(?P<time>\d{4}年\d{2}月\d{2}日\s+\d{2}:\d{2})→(?P<prize>.+?)→
```

**分类**：

- `置顶` → 转发抽奖
- 其余 → 互动抽奖（默认），API 再校

**噪声过滤**：

- 不含 opus 链接的纯 uid 行
- `account.bilibili.com` 链接

### 5.5 `JjunParser`（DS-4 J君名）

**策略**：与 Toolman 类似但更简单

```python
# 1. INITIAL_STATE 提取所有 OPUS rid
# 2. 若前置段落含【置顶抽奖】→ 转发抽奖
# 3. 若 link_text 含「抽奖黑幕」「曝光」「QQ群」→ 丢弃
# 4. 其余 → 互动抽奖
```

**黑名单 link_text 关键词**：

```python
BLACKLIST_TEXT = ("抽奖黑幕", "曝光", "补档", "QQ群", "大会员")
```

### 5.6 `HudongParser`（DS-5 互动抽奖娘）

**策略**：h2 分区 + INITIAL_STATE

```text
遇到 <h2>转发抽奖</h2> 或 ## 转发抽奖 → section=转发抽奖
遇到 ## 预约抽奖 → section=预约抽奖
遇到 ## 互动抽奖 → section=互动抽奖
遇到 ## 充电抽奖 → section=互动抽奖
每个 OPUS 卡片 → 输出一条
```

**关键过滤**：

```python
if dynamic_id == container_meta["container_id"]:
    continue  # 排除合集帖自身
```

---

## 6. 归一化层（Normalizer）

```python
def normalize_link(url_or_id: str) -> str:
    """统一为 18～19 位 dynamic_id 字符串"""
    # t.bilibili.com/(\d{19})
    # bilibili.com/opus/(\d{18,19})
    ...

def normalize_results(items: list[ParseResult], container: dict) -> list[ParseResult]:
    seen = set()
    out = []
    for item in items:
        did = item["dynamic_id"]
        if did in seen:
            continue
        if did == container.get("container_id"):
            continue
        seen.add(did)
        item["source_url"] = f"https://www.bilibili.com/opus/{did}"
        out.append(item)
    return out
```

---

## 7. 归类层（Classifier）

### 7.1 两阶段分类

| 阶段 | 输入 | 输出 |
|------|------|------|
| **初判** | Parser 的 section / 数据源默认值 | `lottery_type` 候选 |
| **终判** | B 站 API 特征 | 校正后的 `lottery_type` |

### 7.2 API 终判规则

```text
拉取 dynamic/detail?id={dynamic_id}
拉取 lottery_notice?business_id={dynamic_id}&business_type=1

若 detail.additional.reserve 存在且 lottery_notice 无数据:
    → 预约抽奖

若 lottery_notice 有数据 或 rich_text 含 RICH_TEXT_NODE_TYPE_LOTTERY:
    若 Parser 初判为 转发抽奖 且 notice 存在:
        → 仍可能为互动抽奖（官方组件）→ 以 notice 为准 → 互动抽奖
    若 notice 有数据:
        → 互动抽奖

若 lottery_notice 无数据 且 无 LOTTERY 组件 且 无 reserve:
    → 转发抽奖（非官方口令类）

若 detail 文案含「转发」「转发动态」且无 notice:
    → 转发抽奖
```

### 7.3 三基类与参与动作映射（供后续模块）

| lottery_type | 参与动作序列（规划） |
|--------------|-------------------|
| 互动抽奖 | `follow` → `repost` → `comment`（或一键参与 API） |
| 转发抽奖 | 解析文案 → 按需 `follow` / `repost` / `comment` |
| 预约抽奖 | `reserve`（预约直播/活动） |

---

## 8. 验证层（Validator）

### 8.1 金标准：`lottery_notice`

```http
GET https://api.vc.bilibili.com/lottery_svr/v1/lottery_svr/lottery_notice
    ?business_id={dynamic_id}&business_type=1
```

| 字段 | 有效条件 |
|------|----------|
| `status` | `0` = 未开奖 |
| `lottery_time` | `> now()` |
| 中奖结果 | 不存在公布名单 |

### 8.2 预约抽奖验证

```http
GET https://api.bilibili.com/x/polymer/web-dynamic/v1/detail?id={dynamic_id}
```

检查 `additional.reserve` 或预约组件状态。

### 8.3 活动状态枚举

```python
class ActivityStatus(Enum):
    ACTIVE = "active"              # 可参与
    EXPIRED = "expired"            # 已开奖
    INVALID = "invalid"            # 非抽奖 / 说明帖
    NEED_CONFIRM = "need_confirm"  # 非官方，需人工规则
```

### 8.4 过滤规则（禁止启发式误杀）

- **禁止**用「发布距今 > N 天」剔除（长周期合法抽奖存在）
- **允许**用 `lottery_notice.status != 0` 剔除
- **允许**用黑名单 link_text 剔除说明帖

---

## 9. 存储设计

### 9.1 SQLite 表结构（建议）

```sql
-- 容器处理水位
CREATE TABLE containers (
    id TEXT PRIMARY KEY,          -- BVxxx / cvxxx / opus_id
    source_id TEXT NOT NULL,
    kind TEXT NOT NULL,           -- video / cv / opus_post
    title TEXT,
    published_at INTEGER,
    processed_at INTEGER,
    url TEXT
);

-- 发现的候选活动
CREATE TABLE activities (
    dynamic_id TEXT PRIMARY KEY,
    source_id TEXT,
    container_id TEXT,
    lottery_type TEXT,            -- 三基类
    lottery_type_final TEXT,      -- API 校正后
    status TEXT,
    source_url TEXT,
    raw_prize TEXT,
    raw_lottery_time TEXT,
    lottery_time INTEGER,         -- API
    first_prize TEXT,             -- API
    participants INTEGER,
    discovered_at INTEGER,
    last_checked_at INTEGER
);

-- 参与记录（预留）
CREATE TABLE participations (
    dynamic_id TEXT PRIMARY KEY,
    participated_at INTEGER,
    action TEXT                   -- follow,repost,comment,reserve
);
```

### 9.2 输出 JSON（供调试）

`data/output/latest_candidates.json`：

```json
{
  "generated_at": "2026-07-12T17:30:00+08:00",
  "sources": {
    "DS-1": { "container": "BV1Z6j76dEKC", "count": 26 },
    "DS-2": { "container": "cv51375456", "count": 138 }
  },
  "activities": [
    {
      "dynamic_id": "1205230628579049477",
      "lottery_type": "互动抽奖",
      "status": "active",
      "source_id": "DS-1",
      "prize": "明日方舟：终末地-贴纸包"
    }
  ]
}
```

---

## 10. 主流程（单次轮询）

```text
for source in SOURCES:
    1. fetch_latest_containers(source)
    2. for container in unprocessed:
           a. raw = download(container)
           b. items = parser.parse(raw, container)
           c. items = normalizer(items, container)
           d. for item in items:
                  item = classifier.finalize(item)   # API
                  item = validator.check(item)
           e. storage.upsert(items)
           f. mark_container_processed(container)
    3. global dedupe by dynamic_id
    4. export latest_candidates.json
    5. log stats
```

---

## 11. 项目目录结构（建议）

```text
bilibili_binggo/
├── config/
│   ├── sources.yaml          # 5 源配置
│   └── settings.yaml         # 间隔、Cookie、限速
├── docs/
│   ├── data-source-analysis.md
│   └── implementation-plan.md
├── src/
│   ├── fetchers/
│   │   ├── video.py          # DS-1
│   │   ├── article.py        # DS-2/3/4
│   │   └── opus_post.py      # DS-5
│   ├── parsers/
│   │   ├── base.py
│   │   ├── video_desc.py
│   │   ├── fanqie.py
│   │   ├── toolman.py
│   │   ├── jjun.py
│   │   └── hudong.py
│   ├── pipeline/
│   │   ├── normalizer.py
│   │   ├── classifier.py
│   │   └── validator.py
│   ├── bilibili/
│   │   ├── client.py         # HTTP 会话、WBI、限速
│   │   ├── lottery.py        # lottery_notice
│   │   └── dynamic.py        # detail API
│   ├── storage/
│   │   └── sqlite.py
│   └── main.py               # CLI 入口
├── data/
│   ├── cache/                # 原始 HTML
│   └── output/               # JSON 结果
├── tests/
│   ├── fixtures/             # 5 源样本 HTML/txt
│   │   ├── ds1_bv1z6_desc.txt
│   │   ├── ds2_cv51375456.html
│   │   ├── ds3_cv51406214.html
│   │   ├── ds4_cv51387129.html
│   │   └── ds5_opus1221421.html
│   └── test_parsers.py       # 快照测试：提取 ID 数量与类型
├── requirements.txt
└── README.md
```

---

## 12. 实施路线图

### Phase 0：基础设施（1～2 天）

- [ ] `bilibili/client.py`：UA、Cookie 加载、限速、错误码处理
- [ ] 落盘 5 份 fixture 样本（从本文档附录 URL 抓取）
- [ ] SQLite schema + 水位表

### Phase 1：解析器（2～3 天）

- [ ] 实现 5 个 Parser + 快照测试
- [ ] 验收标准：每个 fixture 提取 ID 数与人工标注一致（±1）

| Fixture | 预期 ID 数（约） |
|---------|-----------------|
| DS-1 BV1Z6j76dEKC | 26 |
| DS-2 cv51375456 | 138 |
| DS-3 cv51406214 | 40+ |
| DS-4 cv51387129 | 17（有效 ~15） |
| DS-5 opus1221421 | 78 |

### Phase 2：发现层（1～2 天）

- [ ] 5 源 Fetcher + 水位去重
- [ ] DS-5 opus 列表双通道打通

### Phase 3：验证与归类（1～2 天）

- [ ] Classifier 终判
- [ ] Validator + `lottery_notice`
- [ ] 输出 `latest_candidates.json`

### Phase 4：联调与优化（1 天）

- [ ] 端到端轮询
- [ ] DS-3 标题优先级减冗余
- [ ] 日志与监控

### Phase 5：参与模块接口（后续）

- [ ] 按 `lottery_type` 分发到 `actions/repost.py`、`actions/reserve.py`、`actions/interact.py`
- [ ] 读取 `participated` 字段（需 Cookie）

---

## 13. 测试策略

### 13.1 解析器单元测试

```python
def test_fanqie_parser_counts():
    html = read_fixture("ds2_cv51375456.html")
    results = FanqieParser().parse(html, {"container_id": "51375456"})
    ids = {r["dynamic_id"] for r in results}
    assert len(ids) >= 130
    assert count_type(results, "预约抽奖") >= 5
```

### 13.2 回归清单

| 用例 | 预期 |
|------|------|
| DS-1 t 链 | 19 位 ID 全提取 |
| DS-2 上期传送门 | 不计入活动 |
| DS-3 置顶块 | 类型为转发抽奖 |
| DS-4 抽奖黑幕 | 验证后 invalid |
| DS-5 容器自身 ID | 被过滤 |
| 跨源重复 ID | 只保留一条 |

### 13.3 人工抽检

每周从 `latest_candidates.json` 随机抽 20 条：

1. 打开 `source_url` 确认是抽奖动态
2. 核对 `lottery_type` 与页面参与方式
3. 记录准确率

---

## 14. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| API 412 / -509 | 拉取失败 | Cookie + 退避 + 缓存 HTML |
| INITIAL_STATE 结构变更 | 解析失败 | 降级 HTML 正则；告警 |
| DS-5 列表接口需登录 | 漏抓 | 关注 UP 后走 feed/space |
| t 链 ID 格式变化 | DS-1 失败 | 短链 HEAD 跟随跳转取最终 opus |
| 三基类边界模糊（充电/非官方） | 参与动作错误 | 终判以 API 为准；`need_confirm` 人工池 |
| 工具人日更重复 | 性能浪费 | 标题优先级 + dynamic_id 全局去重 |

---

## 15. CLI 设计（预览）

```bash
# 单次全量轮询
python -m src.main poll --all

# 只跑某一源
python -m src.main poll --source DS-2

# 仅解析本地 fixture（开发用）
python -m src.main parse --fixture tests/fixtures/ds2_cv51375456.html --parser fanqie

# 验证某一 dynamic_id
python -m src.main check --id 1221476986669498372
```

---

## 16. 与后续「参与」模块的接口契约

```python
@dataclass
class Activity:
    dynamic_id: str
    lottery_type: Literal["转发抽奖", "预约抽奖", "互动抽奖"]
    status: ActivityStatus
    source_url: str
    lottery_time: int | None
    sender_uid: int | None
    require_follow: bool
    require_repost: bool
    require_comment: bool
    require_reserve: bool
```

参与模块**只消费** `status == active` 的记录，并按 `lottery_type` 选择动作模板。

---

## 17. 文档维护

| 变更 | 更新文档 |
|------|----------|
| UP 更换排版 | `data-source-analysis.md` 对应章节 + fixture |
| 新增第六源 | 两份文档同步扩展 |
| 解析正则调整 | `implementation-plan.md` §5 + 测试预期 |

---

## 18. 总结

本方案的核心设计决策：

1. **五个源、五个 Parser**，不强行统一正则，只在 Normalizer 层统一 `dynamic_id`。
2. **三基类**采用「Parser 初判 + API 终判」双阶段，避免仅靠标题误判。
3. **DS-1 单独处理 t.bilibili.com**，DS-5 单独处理 opus 帖容器，DS-2/3/4 共用 INITIAL_STATE 基础设施。
4. **验证**以 `lottery_notice` 为金标准，避免启发式误杀。
5. **先快照测试、后接 API**，保证链接提取这一环可独立验收。

下一步建议：先完成 **Phase 0 + Phase 1**（落样本 + 五个 Parser 快照测试），通过后再接 Fetcher 与 Validator。
