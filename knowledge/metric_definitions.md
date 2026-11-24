# ���ָ�궨��

�������ݱ���`public.raw_criteo_impression`��Ĭ�ϰ�ԭʼ�ֶ� `campaign` ���飻�����ѯʱ������ `FLOOR(timestamp / 86400.0)::INTEGER + 1`���ﻯ��ͼ `public.ads_campaign_daily` �ж�Ӧ�ļƻ��ֶ���Ϊ `campaign_id`��

���з��ӡ���ĸ����ʹ����ͬ�����ݷ�Χ���ƻ�������ʱ������������ת��ָ�갴��ɸѡ���ع��¼��������ת�� ID ���㣬�����ڰ�ת��������ͳ�ƶ�����

## CTR������ʣ�

- ��ʽ������� / �ع�����
- ���ӣ�`SUM(click)`���ڸ����ݼ��б�ʾ��������ع�����
- ��ĸ��`COUNT(*)`����ʾ�ع��¼����
- ���ݱ���`public.raw_criteo_impression`��
- �����ֶΣ�`campaign`��ÿ��ָ���ٰ���������շ��顣
- SQL��`ROUND(SUM(click)::NUMERIC / NULLIF(COUNT(*), 0), 6)`��
- ���Ϊ�������� `0.05` ��ʾ `5%`�����ĸ���� NULL����ʾ�޷����㣬�������Խ���Ϊ 0��
- ��ͼ�ֶΣ�`ctr`��������ƻ�����ʱ�����¼��� `SUM(clicks)::NUMERIC / NULLIF(SUM(impressions),0)`�����ܼ�ƽ������ CTR��

## ����ת����

- ���壺��ѯ��Χ����Ч��ȥ�ص�ת�� ID ��������������ʾת�� ID ȥ�أ�����֤����ʵҵ���������һһ��Ӧ��
- ���ݱ���`public.raw_criteo_impression`��
- �����ֶΣ�`campaign`��ÿ��ָ���ٰ�����ع������շ��顣
- ��ʽ/SQL��

```sql
COUNT(DISTINCT conversion_id)
    FILTER (WHERE conversion = 1 AND conversion_id <> -1)
```

- ��ͼ�ֶΣ�`unique_conversions`��
- `SUM(conversion)` ��ת�������ع�������������Ϊ��ָ�ꡣ
- ͬһת�� ID ���ܳ����ڶ���ع⡢��������ջ�ƻ��С��������������ת����ʱ����ص�ԭʼ����Ŀ�귶Χ����ȥ�أ�����ֱ���ۼ���ͼ�Ķ���ת������

## ����ת����

- ���壺��ѯ��Χ�ڹ����� Criteo ����Ч��ȥ��ת�� ID ����
- ���ݱ���`public.raw_criteo_impression`��
- �����ֶΣ�`campaign`��ÿ��ָ���ٰ�����ع������շ��顣
- ��ʽ/SQL��

```sql
COUNT(DISTINCT conversion_id)
    FILTER (
        WHERE conversion = 1
          AND attribution = 1
          AND conversion_id <> -1
    )
```

- ��ͼ�ֶΣ�`attributed_conversions`��
- ������ `SUM(attribution)` ���ȥ�ؼ������������Ҳ����ԭʼ������ȥ�ء�

## ����ת��ռ��

- ��ʽ������ת���� / ����ת������
- ���ӣ�ͬһ��Χ������ `conversion=1 AND attribution=1 AND conversion_id<>-1` �Ĳ�ͬת�� ID ����
- ��ĸ��ͬһ��Χ������ `conversion=1 AND conversion_id<>-1` �Ĳ�ͬת�� ID ����
- ���ݱ���`public.raw_criteo_impression`��
- �����ֶΣ�`campaign`��ÿ��ָ���ٰ�����ع������շ��顣
- ��ĸΪ 0 ʱ���� NULL������Ϊû�пɼ���ռ�ȵ���Чת����
- ���ﻯ��ͼÿһ���Ͽɼ��㣺`ROUND(attributed_conversions::NUMERIC / NULLIF(unique_conversions,0),6)`�������ѯ����Ϊ `attributed_conversion_share`���ñ�������ԭʼ�����ﻯ��ͼ���е��С�
- ���졢��ƻ���ռ�ȱ������Ŀ�귶Χ������ȥ�صķ��Ӻͷ�ĸ������ƽ������ռ�ȣ�Ҳ���ܼ����������ת������ֱ����ӡ�

## ת���ɱ�ֵ�ܺ�

- ��ʽ/SQL��`SUM(cost)`��
- ���ݱ���`public.raw_criteo_impression`��
- �����ֶΣ�`campaign`��ÿ��ָ���ٰ�����ع������շ��顣
- ��ͼ�ֶΣ�`transformed_cost_total`��
- ֻ����ת����ĳɱ���ֵ�ܺͣ�û����ʵ���ҵ�λ�����ܳ�Ϊ��ʵ���֧�������ܱ��Ϊ����һ���Ԫ��
- `cpo` �������룬��������� `cost` ���ع�ɱ��ܺ͡�
- �ڲ��ظ��Ҹ���һ�µ��ع�����Ͽ��Լ��ܣ�����������ܳ���΢С������졣

## �����ƻ���������ָ��

������ԭʼ��ֱ�Ӽ��㵱ǰ���ݿⷶΧ�ڵ�ָ�꣬���˳�򰴹��ƻ� ID ���У�

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

ʱ�䷶Χ���ɻش������벻���ƶϵ�ָ��� [business_rules.md](business_rules.md)��

## ȫ����ѯ������Դѡ��

��ǰ���ݿ���ȫ�����롣�ع⡢�����CTR��ת���ɱ�����������������ȴ���ˢ�µ� public.ads_campaign_daily ��ѯ������ CTR �� SUM(clicks)::NUMERIC / NULLIF(SUM(impressions),0) ���㣬�ɱ��� SUM(transformed_cost_total)������ת���͹���ת������/��ƻ�������ԭʼ����Ŀ�귶Χ����ȥ�أ����ܰ�ÿ��ȥ������ӡ�ԭʼ���ɨ������ֻ������ 5 �볬ʱ���ƣ���ҪΪ�������ѯ���зſ���ȫ���ơ�
