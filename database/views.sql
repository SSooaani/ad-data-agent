SELECT
    MIN(timestamp),
    MAX(timestamp),
    MAX(timestamp) / 86400.0 AS approximate_days
FROM raw_criteo_impression;

-- Keep the materialized view definition reusable.
CREATE MATERIALIZED VIEW IF NOT EXISTS ads_campaign_daily AS
SELECT
    FLOOR(timestamp / 86400.0)::INTEGER + 1 AS data_day,

    campaign AS campaign_id,

    COUNT(*) AS impressions,

    SUM(click) AS clicks,

    ROUND(
        SUM(click)::NUMERIC / NULLIF(COUNT(*), 0),
        6
    ) AS ctr,

    COUNT(DISTINCT conversion_id)
        FILTER (
            WHERE conversion = 1
            AND conversion_id <> -1
        ) AS unique_conversions,

    COUNT(DISTINCT conversion_id)
        FILTER (
            WHERE conversion = 1
            AND attribution = 1
            AND conversion_id <> -1
        ) AS attributed_conversions,

    SUM(cost) AS transformed_cost_total

FROM raw_criteo_impression

GROUP BY 1, 2;

SELECT *
FROM ads_campaign_daily
ORDER BY data_day, campaign_id
LIMIT 100;
