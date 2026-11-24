# 广告指标定义

基础数据表：`public.raw_criteo_impression`。默认按原始字段 `campaign` 分组；按天查询时再增加 `FLOOR(timestamp / 86400.0)::INTEGER + 1`。物化视图 `public.ads_campaign_daily` 中对应的计划字段名为 `campaign_id`。

所有分子、分母必须使用相同的数据范围、计划条件和时间条件。下述转化指标按所筛选的曝光记录关联到的转化 ID 计算，不等于按转化发生日统计订单。

## CTR（点击率）

- 公式：点击量 / 曝光量。
- 分子：`SUM(click)`；在该数据集中表示被点击的曝光数。
- 分母：`COUNT(*)`；表示曝光记录数。
- 数据表：`public.raw_criteo_impression`。
- 分组字段：`campaign`；每日指标再按相对数据日分组。
- SQL：`ROUND(SUM(click)::NUMERIC / NULLIF(COUNT(*), 0), 6)`。
- 结果为比例，如 `0.05` 表示 `5%`；零分母返回 NULL，表示无法计算，不能擅自解释为 0。
- 视图字段：`ctr`；跨天或跨计划汇总时须重新计算 `SUM(clicks)::NUMERIC / NULLIF(SUM(impressions),0)`，不能简单平均各行 CTR。

## 独立转化数

- 含义：查询范围内有效、去重的转化 ID 数；“独立”表示转化 ID 去重，不保证与现实业务独立订单一一对应。
- 数据表：`public.raw_criteo_impression`。
- 分组字段：`campaign`；每日指标再按相对曝光数据日分组。
- 公式/SQL：

```sql
COUNT(DISTINCT conversion_id)
    FILTER (WHERE conversion = 1 AND conversion_id <> -1)
```

- 视图字段：`unique_conversions`。
- `SUM(conversion)` 是转化正例曝光行数，不能作为该指标。
- 同一转化 ID 可能出现在多个曝光、多个数据日或计划中。跨组求整体独立转化数时，须回到原始表在目标范围重新去重，不能直接累加视图的独立转化数。

## 归因转化数

- 含义：查询范围内归因于 Criteo 的有效、去重转化 ID 数。
- 数据表：`public.raw_criteo_impression`。
- 分组字段：`campaign`；每日指标再按相对曝光数据日分组。
- 公式/SQL：

```sql
COUNT(DISTINCT conversion_id)
    FILTER (
        WHERE conversion = 1
          AND attribution = 1
          AND conversion_id <> -1
    )
```

- 视图字段：`attributed_conversions`。
- 不能用 `SUM(attribution)` 替代去重计数；跨组汇总也须在原始表重新去重。

## 归因转化占比

- 公式：归因转化数 / 独立转化数。
- 分子：同一范围内满足 `conversion=1 AND attribution=1 AND conversion_id<>-1` 的不同转化 ID 数。
- 分母：同一范围内满足 `conversion=1 AND conversion_id<>-1` 的不同转化 ID 数。
- 数据表：`public.raw_criteo_impression`。
- 分组字段：`campaign`；每日指标再按相对曝光数据日分组。
- 分母为 0 时返回 NULL，含义为没有可计算占比的有效转化。
- 在物化视图每一行上可计算：`ROUND(attributed_conversions::NUMERIC / NULLIF(unique_conversions,0),6)`，建议查询别名为 `attributed_conversion_share`。该别名不是原始表或物化视图已有的列。
- 跨天、跨计划的占比必须基于目标范围内重新去重的分子和分母，不能平均各行占比，也不能假设逐组独立转化数可直接相加。

## 转换成本值总和

- 公式/SQL：`SUM(cost)`。
- 数据表：`public.raw_criteo_impression`。
- 分组字段：`campaign`；每日指标再按相对曝光数据日分组。
- 视图字段：`transformed_cost_total`。
- 只描述转换后的成本数值总和，没有真实货币单位；不能称为真实广告支出，不能标记为人民币或美元。
- `cpo` 不是收入，不用于替代 `cost` 求曝光成本总和。
- 在不重复且覆盖一致的曝光分组上可以加总；浮点运算可能出现微小舍入差异。

## 按广告计划计算五项指标

下例从原始表直接计算当前数据库范围内的指标，结果顺序按广告计划 ID 排列：

```sql
WITH campaign_metrics AS (
    SELECT
        campaign,
        COUNT(*) AS impressions,
        SUM(click) AS clicks,
        COUNT(DISTINCT conversion_id)
            FILTER (WHERE conversion = 1 AND conversion_id <> -1)
            AS unique_conversions,
        COUNT(DISTINCT conversion_id)
            FILTER (
                WHERE conversion = 1
                  AND attribution = 1
                  AND conversion_id <> -1
            ) AS attributed_conversions,
        SUM(cost) AS transformed_cost_total
    FROM public.raw_criteo_impression
    GROUP BY campaign
)
SELECT
    campaign,
    ROUND(clicks::NUMERIC / NULLIF(impressions, 0), 6) AS ctr,
    unique_conversions,
    attributed_conversions,
    ROUND(
        attributed_conversions::NUMERIC / NULLIF(unique_conversions, 0),
        6
    ) AS attributed_conversion_share,
    transformed_cost_total
FROM campaign_metrics
ORDER BY campaign;
```

时间范围、可回答问题与不可推断的指标见 [business_rules.md](business_rules.md)。

## 全量查询的数据源选择

当前数据库已全量导入。曝光、点击、CTR、转换成本及其相对日趋势优先从已刷新的 public.ads_campaign_daily 查询：跨天 CTR 用 SUM(clicks)::NUMERIC / NULLIF(SUM(impressions),0) 重算，成本用 SUM(transformed_cost_total)。独立转化和归因转化跨日/跨计划仍须在原始表的目标范围重新去重，不能把每日去重数相加。原始大表扫描仍受只读工具 5 秒超时限制；不要为完成慢查询自行放宽安全限制。
