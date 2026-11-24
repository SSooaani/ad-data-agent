"""Independent full-import checks and read-only MCP-tool smoke checks; no LLM calls."""
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import sys
import time

import pandas as pd
from pandas.testing import assert_frame_equal
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.db import get_engine
from database.import_sample import COLUMNS
from database.import_full import table_binary_sha256
from ad_agent.tools import schema_search, sql_validate, sql_execute, result_analyze
from rag.chunks import document_hashes


def main():
    report = json.loads((ROOT / 'database/full_import_report.json').read_text(encoding='utf-8'))
    assert report['phase'] == 'complete' and report['rows'] == 16_468_027
    engine = get_engine()
    # Mark pages all-visible for safe, fast count/index-only reads after bulk loading.
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.exec_driver_sql('VACUUM (ANALYZE) public.raw_criteo_impression')
    with engine.connect() as conn:
        conn.exec_driver_sql('SET TRANSACTION READ ONLY')
        stats = dict(conn.execute(text('''
            SELECT COUNT(*) AS rows,MIN(timestamp) AS min_timestamp,MAX(timestamp) AS max_timestamp,
                   COUNT(DISTINCT campaign) AS campaigns,
                   COUNT(DISTINCT conversion_id) FILTER (WHERE conversion=1 AND conversion_id<>-1) AS unique_conversions,
                   COUNT(DISTINCT conversion_id) FILTER (WHERE conversion=1 AND attribution=1 AND conversion_id<>-1) AS attributed_conversions
            FROM public.raw_criteo_impression
        ''')).mappings().one())
        assert stats['rows'] == report['statistics']['rows']
        columns = ','.join(f'"{name}"' for name in COLUMNS)
        original_sample = pd.read_parquet(ROOT / 'data/interim/criteo_sample.parquet')
        prefix = pd.read_sql_query(text(f'SELECT {columns} FROM public.raw_criteo_impression WHERE row_id<=200000 ORDER BY row_id'), conn)
        assert_frame_equal(original_sample, prefix, check_exact=True)
        daily = pd.read_sql_query(text('SELECT * FROM public.ads_campaign_daily ORDER BY data_day,campaign_id'), conn)
        assert_frame_equal(daily, pd.read_parquet(ROOT / 'data/processed/campaign_daily.parquet'), check_exact=True)
        assert int(daily.impressions.sum()) == stats['rows']
        expected_last7 = [dict(row) for row in conn.execute(text('''
            WITH b AS (SELECT MAX(FLOOR(timestamp/86400.0)::INTEGER+1) AS last_day FROM public.raw_criteo_impression)
            SELECT FLOOR(timestamp/86400.0)::INTEGER+1 AS data_day, SUM(click) AS clicks
            FROM public.raw_criteo_impression CROSS JOIN b
            WHERE FLOOR(timestamp/86400.0)::INTEGER+1 BETWEEN GREATEST(1,b.last_day-6) AND b.last_day
            GROUP BY data_day ORDER BY data_day
        ''')).mappings()]
        grants = dict(conn.execute(text('''
            SELECT has_table_privilege('criteo_reader','public.raw_criteo_impression','SELECT') AS raw_select,
                   has_table_privilege('criteo_reader','public.ads_campaign_daily','SELECT') AS daily_select,
                   has_table_privilege('criteo_reader','public.raw_criteo_impression','INSERT,UPDATE,DELETE') AS writes
        ''')).mappings().one())
        assert grants == {'raw_select': True, 'daily_select': True, 'writes': False}
        backup = report['backup_table'].removeprefix('public.')
        assert re.fullmatch(r'criteo_sample_backup_\d{8}_\d{6}', backup)
        assert table_binary_sha256(conn, backup) == report['previous_sample_binary_sha256']
        sequence = conn.exec_driver_sql('SELECT last_value,is_called FROM public.raw_criteo_impression_row_id_seq').one()
        assert tuple(sequence) == (stats['rows'] + 1, False)
    engine.dispose()
    assert schema_search('campaign��click��timestamp', 'raw_criteo_impression')['found']
    query = '''WITH b AS (SELECT MAX(data_day) AS last_day FROM public.ads_campaign_daily)
        SELECT data_day,SUM(clicks) AS clicks FROM public.ads_campaign_daily CROSS JOIN b
        WHERE data_day BETWEEN GREATEST(1,b.last_day-6) AND b.last_day
        GROUP BY data_day ORDER BY data_day LIMIT 7'''
    assert sql_validate(query)['valid']
    started = time.monotonic()
    result = sql_execute(query)
    seconds = time.monotonic() - started
    assert result['ok'], result
    normalized = [{'data_day': int(row['data_day']), 'clicks': int(row['clicks'])} for row in result['rows']]
    assert normalized == expected_last7, (result['rows'], expected_last7)
    analysis = result_analyze(result['result_id'])
    assert analysis['records'] == result['rows']
    count_result = sql_execute('SELECT COUNT(*) AS impressions FROM public.raw_criteo_impression LIMIT 1')
    index = json.loads((ROOT / 'rag/index_manifest.json').read_text(encoding='utf-8'))
    assert index['document_sha256'] == document_hashes()
    checks = {
        'verified_at': datetime.now(timezone.utc).isoformat(), 'passed': True,
        'statistics': stats, 'daily_rows': len(daily),
        'first_data_day': int(daily.data_day.min()), 'last_data_day': int(daily.data_day.max()),
        'daily_impressions_match_raw': True, 'sample_prefix_unchanged': True,
        'daily_parquet_matches_view': True, 'reader_grants': grants,
        'sample_backup_hash_verified': True, 'next_generated_row_id': int(sequence[0]),
        'last_seven_data_days': result['rows'], 'mcp_tool_query_seconds': round(seconds,3),
        'raw_count_under_5s': count_result['ok'],
        'raw_count_result': count_result.get('rows'), 'raw_count_error': count_result.get('error'),
        'rag_index_current': True, 'rag_chunks': index['chunks'],
        'external_llm_calls': 0,
    }
    (ROOT / 'database/full_import_verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(checks,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
