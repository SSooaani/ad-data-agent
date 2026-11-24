# 业务规则与回答边界

适用范围：Criteo 曝光原始表 `public.raw_criteo_impression` 和每日计划物化视图 `public.ads_campaign_daily`。字段以 [table_schema.md](table_schema.md) 为准，指标以 [metric_definitions.md](metric_definitions.md) 为准。

## 数据粒度与标记

1. 一行数据代表一次广告曝光。`row_id` 为本地生成的记录编号，不是 Criteo 原始字段或订单 ID。
2. `click` 只能取 0 或 1，表示该曝光是否被点击。`SUM(click)` 是被点击的曝光数量；不能据此还原每次点击的独立事件明细或精确点击时间。出现 NULL 或其他值时需报告数据质量问题。
3. `conversion_id=-1` 表示没有对应转化 ID，不能把 -1 当作一笔转化计入去重数。原始哨兵值应保留，不擅自改成 0。
4. `conversion` 和 `attribution` 为 0/1 标记。`conversion=1` 表示曝光后 30 天内有转化；多条曝光记录可关联同一转化 ID。独立转化数需要过滤有效 ID 后去重，不能用正例曝光行数冒充独立订单数。
5. 广告计划的原始字段为 `campaign`；`campaign_id` 只是每日物化视图中的别名。不得虚构 `ad_id`、产品、行业或地区等不存在的字段，也不根据 `cat1`–`cat9` 猜测业务含义。

## 时间解释

6. `timestamp` 是曝光的相对秒数，不是真实日历日期或 Unix 时间戳。不能使用 `to_timestamp(timestamp)` 推断真实年月日，也不能使用当前系统日期筛选这份数据。
7. 相对数据日定义为 `FLOOR(timestamp / 86400.0)::INTEGER + 1`。每日视图按曝光数据日聚合，转化指标表示这些曝光关联的转化，不等于该日实际发生的订单数。
8. “最近七天”必须解释为当前数据库数据时间轴最后七个相对数据日，包含最后一个数据日。默认以整个原始表的最大曝光时间确定末日，再施加广告计划等筛选；不能默认使用当前日期往前推七天。
9. 默认窗口为 `data_day BETWEEN GREATEST(1, max_data_day-6) AND max_data_day`。这是相对数据日窗口，不是滚动 168 小时；若用户明确要求滚动 168 小时，应另行说明并使用秒级时间条件。
10. 数据不足七天时，只报告实际覆盖的天数和范围，不补造七天数据、不把缺失日自动当成零。若原始表为空，应说明没有可查询的数据。

最近七个相对数据日的曝光量与点击量查询示例：

```sql
WITH bounds AS (
    SELECT MAX(FLOOR(timestamp / 86400.0)::INTEGER + 1) AS max_data_day
    FROM public.raw_criteo_impression
), scoped AS (
    SELECT
        r.*,
        FLOOR(r.timestamp / 86400.0)::INTEGER + 1 AS data_day
    FROM public.raw_criteo_impression r
    CROSS JOIN bounds b
    WHERE FLOOR(r.timestamp / 86400.0)::INTEGER + 1
          BETWEEN GREATEST(1, b.max_data_day - 6) AND b.max_data_day
)
SELECT
    data_day,
    campaign,
    COUNT(*) AS impressions,
    SUM(click) AS clicks
FROM scoped
GROUP BY data_day, campaign
ORDER BY data_day, campaign;
```

原始表已导入完整数据集，共 16,468,027 条曝光、675 个 campaign；曝光 timestamp 范围 0–2,671,199 秒，覆盖 data_day=1–31，共 31 个相对数据日。当前“最近七天”默认对应相对数据日 25–31，需要实际查询后报告；不能转换为真实日历日期，也不能默认首末数据日都完整。

## 成本、收入与指标限制

11. `cost`、`cpo` 都是转换后的数值，不是实际货币金额。`SUM(cost)` 只能称为“转换成本值总和”，不能报告为真实广告支出；也不能把 `cpo` 当作实际收入。
12. ROAS 需要收入与广告支出。本数据缺少收入字段，且成本数值经过转换，因此无法计算真实 ROAS，不能编造收入或用 `cpo` 代替收入。
13. 可以回答：已导入数据范围内的曝光数、被点击曝光数、CTR、有效转化 ID 去重数、归因转化 ID 去重数、归因转化占比、转换成本值总和及相对时间趋势。
14. 不能直接回答：真实日历日期表现、真实货币广告支出/收入、真实 ROAS、完整独立点击事件轨迹、匿名上下文特征的未公开业务含义。需要说明缺失字段和原因。

## 聚合与回答要求

15. CTR 的分母为曝光量；归因转化占比的分母为独立转化数。零分母返回 NULL，说明无法计算，不强行填 0。比例转成百分数时须明确展示单位。
16. 多个曝光、数据日或广告计划可能关联同一转化 ID；跨组统计独立转化或归因转化必须在目标范围重新去重，不能直接累加每日计划视图中的去重计数。跨组 CTR 应按总点击量 / 总曝光量重算。
17. 每日物化视图需要刷新后才反映原始表变化。回答时需说明使用原始表还是物化视图，以及统计范围；无法确认视图是否最新时，不声称它反映最新导入结果。
18. 当前数据库已完成全量导入。data/interim/criteo_sample.parquet 仍保留初期前 200,000 条顺序样本；此前基于该样本的 Agent 评测属于历史结果，不能冒充全量评测结论。
