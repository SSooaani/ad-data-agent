# 真实数据库结构与字段字典

核对日期：2026-11-24。依据：本机 PostgreSQL `criteo_ads` 的系统目录、实际物化视图定义，以及 [Criteo 官方字段说明](https://ailab.criteo.com/criteo-attribution-modeling-bidding-dataset/)。

## 原始曝光表：public.raw_criteo_impression

粒度：一行代表一次广告曝光。原始数据有 22 个字段，数据库额外生成 `row_id`，因此实际表共 23 列。原始字段名及顺序保持不变。

| 数据库顺序 | 字段 | PostgreSQL 类型 | 含义与取值说明 |
| --- | --- | --- | --- |
| 1 | row_id | BIGINT（BIGSERIAL） | 本地自动生成的记录编号，主键、非空，默认从序列取值；不属于 Criteo 原始字段，也不是订单 ID。 |
| 2 | timestamp | BIGINT | 曝光相对时间标记，单位秒，数据起点为 0；不是实际日历日期或 Unix 时间戳。 |
| 3 | uid | BIGINT | 匿名用户 ID。 |
| 4 | campaign | BIGINT | 原始广告计划 ID。 |
| 5 | conversion | SMALLINT | 0/1，曝光后 30 天内是否发生转化；正例行不等于独立订单。 |
| 6 | conversion_timestamp | BIGINT | 转化时间标记；未观察到转化时为 -1。 |
| 7 | conversion_id | BIGINT | 转化唯一编号；相关曝光可重复引用同一编号，-1 表示没有对应转化 ID。 |
| 8 | attribution | SMALLINT | 0/1，转化是否归因于 Criteo。 |
| 9 | click | SMALLINT | 0/1，当前曝光是否被点击；不是独立点击事件记录。 |
| 10 | click_pos | INTEGER | 转化前点击序列中的位置，0 为首次点击；保留原始 -1 哨兵值，不解释为广告位。 |
| 11 | click_nb | INTEGER | 转化前的点击次数；保留原始 -1 哨兵值。 |
| 12 | cost | DOUBLE PRECISION | 转换后的曝光成本值，不是真实货币金额。 |
| 13 | cpo | DOUBLE PRECISION | 转换后的每单成本值，不是真实货币金额，也不是收入。 |
| 14 | time_since_last_click | BIGINT | 距离上次点击的时间，单位秒；保留原始 -1 哨兵值。 |
| 15 | cat1 | BIGINT | 匿名上下文类别特征 1，业务含义未公开。 |
| 16 | cat2 | BIGINT | 匿名上下文类别特征 2，业务含义未公开。 |
| 17 | cat3 | BIGINT | 匿名上下文类别特征 3，业务含义未公开。 |
| 18 | cat4 | BIGINT | 匿名上下文类别特征 4，业务含义未公开。 |
| 19 | cat5 | BIGINT | 匿名上下文类别特征 5，业务含义未公开。 |
| 20 | cat6 | BIGINT | 匿名上下文类别特征 6，业务含义未公开。 |
| 21 | cat7 | BIGINT | 匿名上下文类别特征 7，业务含义未公开。 |
| 22 | cat8 | BIGINT | 匿名上下文类别特征 8，业务含义未公开。 |
| 23 | cat9 | BIGINT | 匿名上下文类别特征 9，业务含义未公开。 |

实际数据库只有 `row_id` 声明了非空和主键；其余 22 列在表结构上允许 NULL。`click` 等标记的 0/1 限制是数据规则，不应误称为数据库已建立的 CHECK 约束。

原始 TSV 带有表头；表头从 `timestamp` 开始，共 22 列，不包含 `row_id`。读取时须校验表头并跳过它。

## 每日计划物化视图：public.ads_campaign_daily

粒度：每个相对数据日、每个广告计划一行，共 8 列。视图由 `public.raw_criteo_impression` 聚合生成，不会自动随原始表更新；刷新命令为 `REFRESH MATERIALIZED VIEW public.ads_campaign_daily;`。

| 顺序 | 字段 | PostgreSQL 类型 | 来源/含义 |
| --- | --- | --- | --- |
| 1 | data_day | INTEGER | `FLOOR(timestamp / 86400.0)::INTEGER + 1`，从第 1 个相对数据日开始。 |
| 2 | campaign_id | BIGINT | 原始字段 `campaign` 的视图别名；查询原始表时仍用 `campaign`。 |
| 3 | impressions | BIGINT | `COUNT(*)`，曝光记录数。 |
| 4 | clicks | BIGINT | `SUM(click)`，被点击的曝光数。 |
| 5 | ctr | NUMERIC | 点击量 / 曝光量，保留 6 位小数，存储为比例。 |
| 6 | unique_conversions | BIGINT | 当前计划、当前曝光数据日内，`conversion=1` 且 `conversion_id<>-1` 的不同转化 ID 数。 |
| 7 | attributed_conversions | BIGINT | 在独立转化数条件上增加 `attribution=1` 后去重计数。 |
| 8 | transformed_cost_total | DOUBLE PRECISION | `SUM(cost)`，转换成本值之和，非真实货币支出。 |

归因转化占比属于查询时派生指标，目前不是该物化视图的实际字段。定义见 [metric_definitions.md](metric_definitions.md)。

## 当前数据范围

原始表已导入完整数据集，共 16,468,027 条曝光、675 个 campaign；曝光 timestamp 范围 0–2,671,199 秒，覆盖 data_day=1–31，共 31 个相对数据日。这是当前全量数据库范围；20 万条 Parquet 开发样本仍单独保留，不能与当前数据库范围混淆。详细校验见 database/full_import_report.json。

不存在可直接使用的收入、真实日历日期、真实币种金额字段；不要虚构相关列。业务边界见 [business_rules.md](business_rules.md)。
