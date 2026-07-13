# CLI 命令手册

## 总览
```bash
python scripts/bili_login.py # 哔哩哔哩扫码登录
python scripts/check_ds1.py # DS-1 哔哩抽奖小助理更新检查
python scripts/check_ds2.py # DS-2 番茄薯条喵更新检查
python scripts/check_ds3.py # DS-3 你的抽奖工具人更新检查
python scripts/check_ds4.py # DS-4 J君名更新检查
python scripts/check_ds5.py # DS-5 互动抽奖娘更新检查
python scripts/check_ds6.py # DS-6 糯米是个背包更新检查
python scripts/merge_links.py # 合并六个数据源的活动链接
python scripts/classify_links.py # 活动链接抽奖类型分类
python scripts/fetch_activity_info.py # 抽奖活动信息拉取
python scripts/participate.py # 参与活动（互动/转发/预约）
python scripts/run_dashboard.py # 本地 Web 控制台
```


## `bili_login.py`

**说明**：哔哩哔哩扫码登录

**指令**：

```bash
python scripts/bili_login.py
```

**功能**：用手机 App 扫码登录，保存 Cookie 供后续脚本使用。

## `check_ds1.py`

**说明**：DS-1 哔哩抽奖小助理更新检查

**指令**：

```bash
python scripts/check_ds1.py
python scripts/check_ds1.py --force
```

**功能**：检查最新投稿视频是否更新，有更新时从简介提取活动链接；`--force` 强制重新解析当前最新视频。

## `check_ds2.py`

**说明**：DS-2 番茄薯条喵更新检查

**指令**：

```bash
python scripts/check_ds2.py
python scripts/check_ds2.py --force
```

**功能**：检查最新专栏是否更新，有更新时从正文提取活动链接；`--force` 强制重新解析当前最新专栏。

## `check_ds3.py`

**说明**：DS-3 你的抽奖工具人更新检查

**指令**：

```bash
python scripts/check_ds3.py
python scripts/check_ds3.py --force
```

**功能**：检查最新专栏是否更新，有更新时从正文提取活动链接；`--force` 强制重新解析当前最新专栏。

## `check_ds4.py`

**说明**：DS-4 J君名更新检查

**指令**：

```bash
python scripts/check_ds4.py
python scripts/check_ds4.py --force
```

**功能**：检查最新专栏是否更新，有更新时从正文提取活动链接；`--force` 强制重新解析当前最新专栏。

## `check_ds5.py`

**说明**：DS-5 互动抽奖娘更新检查

**指令**：

```bash
python scripts/check_ds5.py
python scripts/check_ds5.py --force
```

**功能**：检查最新 Opus 帖是否更新，有更新时从正文提取活动链接；`--force` 强制重新解析当前最新 Opus 帖。

## `check_ds6.py`

**说明**：DS-6 糯米是个背包更新检查

**指令**：

```bash
python scripts/check_ds6.py
python scripts/check_ds6.py --force
```

**功能**：检查最新 Opus 专栏是否更新，有更新时从正文提取活动链接（含互动/预约分区提示）；`--force` 强制重新解析当前最新专栏。

## `merge_links.py`

**说明**：合并六个数据源的活动链接

**指令**：

```bash
python scripts/merge_links.py
```

**功能**：读取六个数据源的最新结果，按动态 ID 去重合并，写入 `data/output/merged_latest.json`。输出中包含 `new_activity_ids` / `new_count`，用于标识尚未出现在 `enriched_latest.json` 中的新链接。

## `classify_links.py`

**说明**：活动链接抽奖类型分类

**指令**：

```bash
python scripts/classify_links.py
python scripts/classify_links.py --force
```

**功能**：读取合并结果，通过 B 站 API 将每条活动归类为转发抽奖、预约抽奖或互动抽奖，写入 `data/output/classified_latest.json`。默认仅对 `classified_latest.json` 中尚未出现的新链接发起分类，已有记录直接复用；`--force` 忽略缓存并全量重跑。

## `fetch_activity_info.py`

**说明**：抽奖活动信息拉取（P1+P2+P3）

**指令**：

```bash
python scripts/fetch_activity_info.py
python scripts/fetch_activity_info.py --force
```

**功能**：读取分类结果，对互动/预约抽奖调用 `lottery_notice` 拉取奖品、开奖时间、抽取人数、中奖名单；对转发抽奖提取动态正文并由 LLM 纯解析奖品、开奖时间、参与条件、抽取人数。转发类活动状态默认 `未参加`；互动/预约类根据 B 站接口或参与记录判断。默认仅初始化 `enriched_latest.json` 中尚未存在的新活动；已有记录复用并同步参与状态。已结束活动走缓存；`--force` 全量重拉。

## `participate.py`

**说明**：参与活动（P4）

**指令**：

```bash
python scripts/participate.py 1208931614786060297
```

**功能**：根据 `enriched_latest.json` 自动识别活动类型。互动/转发类依次执行五项操作（点赞 → 关注 → 收藏 → 转发 → 评论），预约类执行预约点击；已完成项会跳过，避免重复点击取消状态。参与成功后自动更新 `enriched_latest.json`、`data/participations.json` 与 `data/participation_actions.json`。

## `run_dashboard.py`

**说明**：本地 Web 控制台

**指令**：

```bash
python scripts/run_dashboard.py
```

**功能**：在 `http://127.0.0.1:8787` 启动本地面板。展示 B 站账号信息（昵称、头像、关注/动态/私信未读、登录是否过期），提供「一键更新活动链接」（增量检查六个数据源 → 合并 → 分类 → 拉取详情，历史记录全部保留），以及可筛选的活动状态表与单行参与操作。参与状态按登录 UID 分目录存储。所有任务均为手动触发，同一时间只运行一个任务。
