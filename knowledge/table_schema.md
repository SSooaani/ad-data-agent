# ��ʵ���ݿ�ṹ���ֶ��ֵ�

�˶����ڣ�2026-11-24�����ݣ����� PostgreSQL `criteo_ads` ��ϵͳĿ¼��ʵ���ﻯ��ͼ���壬�Լ� [Criteo �ٷ��ֶ�˵��](https://ailab.criteo.com/criteo-attribution-modeling-bidding-dataset/)��

## ԭʼ�ع����public.raw_criteo_impression

���ȣ�һ�д���һ�ι���ع⡣ԭʼ������ 22 ���ֶΣ����ݿ�������� `row_id`�����ʵ�ʱ��� 23 �С�ԭʼ�ֶ�����˳�򱣳ֲ��䡣

| ���ݿ�˳�� | �ֶ� | PostgreSQL ���� | ������ȡֵ˵�� |
| --- | --- | --- | --- |
| 1 | row_id | BIGINT��BIGSERIAL�� | �����Զ����ɵļ�¼��ţ��������ǿգ�Ĭ�ϴ�����ȡֵ�������� Criteo ԭʼ�ֶΣ�Ҳ���Ƕ��� ID�� |
| 2 | timestamp | BIGINT | �ع����ʱ���ǣ���λ�룬�������Ϊ 0������ʵ���������ڻ� Unix ʱ����� |
| 3 | uid | BIGINT | �����û� ID�� |
| 4 | campaign | BIGINT | ԭʼ���ƻ� ID�� |
| 5 | conversion | SMALLINT | 0/1���ع�� 30 �����Ƿ���ת���������в����ڶ��������� |
| 6 | conversion_timestamp | BIGINT | ת��ʱ���ǣ�δ�۲쵽ת��ʱΪ -1�� |
| 7 | conversion_id | BIGINT | ת��Ψһ��ţ�����ع���ظ�����ͬһ��ţ�-1 ��ʾû�ж�Ӧת�� ID�� |
| 8 | attribution | SMALLINT | 0/1��ת���Ƿ������ Criteo�� |
| 9 | click | SMALLINT | 0/1����ǰ�ع��Ƿ񱻵�������Ƕ�������¼���¼�� |
| 10 | click_pos | INTEGER | ת��ǰ��������е�λ�ã�0 Ϊ�״ε��������ԭʼ -1 �ڱ�ֵ��������Ϊ���λ�� |
| 11 | click_nb | INTEGER | ת��ǰ�ĵ������������ԭʼ -1 �ڱ�ֵ�� |
| 12 | cost | DOUBLE PRECISION | ת������ع�ɱ�ֵ��������ʵ���ҽ� |
| 13 | cpo | DOUBLE PRECISION | ת�����ÿ���ɱ�ֵ��������ʵ���ҽ�Ҳ�������롣 |
| 14 | time_since_last_click | BIGINT | �����ϴε����ʱ�䣬��λ�룻����ԭʼ -1 �ڱ�ֵ�� |
| 15 | cat1 | BIGINT | ����������������� 1��ҵ����δ������ |
| 16 | cat2 | BIGINT | ����������������� 2��ҵ����δ������ |
| 17 | cat3 | BIGINT | ����������������� 3��ҵ����δ������ |
| 18 | cat4 | BIGINT | ����������������� 4��ҵ����δ������ |
| 19 | cat5 | BIGINT | ����������������� 5��ҵ����δ������ |
| 20 | cat6 | BIGINT | ����������������� 6��ҵ����δ������ |
| 21 | cat7 | BIGINT | ����������������� 7��ҵ����δ������ |
| 22 | cat8 | BIGINT | ����������������� 8��ҵ����δ������ |
| 23 | cat9 | BIGINT | ����������������� 9��ҵ����δ������ |

ʵ�����ݿ�ֻ�� `row_id` �����˷ǿպ����������� 22 ���ڱ��ṹ������ NULL��`click` �ȱ�ǵ� 0/1 ���������ݹ��򣬲�Ӧ���Ϊ���ݿ��ѽ����� CHECK Լ����

ԭʼ TSV ���б�ͷ����ͷ�� `timestamp` ��ʼ���� 22 �У������� `row_id`����ȡʱ��У���ͷ����������

## ÿ�ռƻ��ﻯ��ͼ��public.ads_campaign_daily

���ȣ�ÿ����������ա�ÿ�����ƻ�һ�У��� 8 �С���ͼ�� `public.raw_criteo_impression` �ۺ����ɣ������Զ���ԭʼ�����£�ˢ������Ϊ `REFRESH MATERIALIZED VIEW public.ads_campaign_daily;`��

| ˳�� | �ֶ� | PostgreSQL ���� | ��Դ/���� |
| --- | --- | --- | --- |
| 1 | data_day | INTEGER | `FLOOR(timestamp / 86400.0)::INTEGER + 1`���ӵ� 1 ����������տ�ʼ�� |
| 2 | campaign_id | BIGINT | ԭʼ�ֶ� `campaign` ����ͼ��������ѯԭʼ��ʱ���� `campaign`�� |
| 3 | impressions | BIGINT | `COUNT(*)`���ع��¼���� |
| 4 | clicks | BIGINT | `SUM(click)`����������ع����� |
| 5 | ctr | NUMERIC | ����� / �ع��������� 6 λС�����洢Ϊ������ |
| 6 | unique_conversions | BIGINT | ��ǰ�ƻ�����ǰ�ع��������ڣ�`conversion=1` �� `conversion_id<>-1` �Ĳ�ͬת�� ID ���� |
| 7 | attributed_conversions | BIGINT | �ڶ���ת�������������� `attribution=1` ��ȥ�ؼ����� |
| 8 | transformed_cost_total | DOUBLE PRECISION | `SUM(cost)`��ת���ɱ�ֵ֮�ͣ�����ʵ����֧���� |

����ת��ռ�����ڲ�ѯʱ����ָ�꣬Ŀǰ���Ǹ��ﻯ��ͼ��ʵ���ֶΡ������ [metric_definitions.md](metric_definitions.md)��

## ��ǰ���ݷ�Χ

ԭʼ���ѵ����������ݼ����� 16,468,027 ���ع⡢675 �� campaign���ع� timestamp ��Χ 0�C2,671,199 �룬���� data_day=1�C31���� 31 ����������ա����ǵ�ǰȫ�����ݿⷶΧ��20 ���� Parquet ���������Ե��������������뵱ǰ���ݿⷶΧ��������ϸУ��� database/full_import_report.json��

�����ڿ�ֱ��ʹ�õ����롢��ʵ�������ڡ���ʵ���ֽ���ֶΣ���Ҫ�鹹����С�ҵ��߽�� [business_rules.md](business_rules.md)��
