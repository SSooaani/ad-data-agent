"""Real PostgreSQL execution plus adversarial SQL-policy checks; no external LLM."""
import json
from pathlib import Path
import sys
import time
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ad_agent.tools import schema_search, sql_validate, sql_execute, result_analyze
from database.readonly import get_readonly_engine
from sqlalchemy.exc import DBAPIError

BAD_SQL = [
    'DELETE FROM raw_criteo_impression',
    'UPDATE raw_criteo_impression SET click=0',
    'DROP TABLE raw_criteo_impression',
    'CREATE TABLE accidental (x INT)',
    'SELECT * FROM raw_criteo_impression LIMIT 1; DELETE FROM raw_criteo_impression',
    'WITH x AS (DELETE FROM raw_criteo_impression RETURNING *) SELECT * FROM x LIMIT 1',
    'SELECT * INTO accidental FROM raw_criteo_impression LIMIT 1',
    'SELECT * FROM raw_criteo_impression LIMIT 1 FOR UPDATE',
    'SELECT * FROM raw_criteo_impression LIMIT 1 FOR SHARE',
    'SELECT * FROM pg_catalog.pg_roles LIMIT 1',
    'SELECT * FROM information_schema.columns LIMIT 1',
    'SELECT * FROM private.raw_criteo_impression LIMIT 1',
    'SELECT * FROM absent_table LIMIT 1',
    'SELECT missing_column FROM raw_criteo_impression LIMIT 1',
    'SELECT b.click FROM raw_criteo_impression a LIMIT 1',
    'SELECT a.click FROM raw_criteo_impression a JOIN ads_campaign_daily b ON a.campaign=b.missing LIMIT 1',
    'WITH x AS (SELECT campaign FROM raw_criteo_impression) SELECT nope FROM x LIMIT 1',
    'SELECT campaign FROM raw_criteo_impression UNION ALL SELECT missing FROM ads_campaign_daily LIMIT 1',
    'SELECT * FROM raw_criteo_impression',
    'SELECT * FROM (SELECT * FROM raw_criteo_impression LIMIT 1) x',
    'SELECT * FROM raw_criteo_impression LIMIT 1001',
    'SELECT * FROM raw_criteo_impression LIMIT ALL',
    'SELECT * FROM raw_criteo_impression LIMIT -1',
    'SELECT * FROM raw_criteo_impression LIMIT (SELECT 1)',
    "SELECT set_config('default_transaction_read_only','off',false) FROM raw_criteo_impression LIMIT 1",
    "SELECT nextval('raw_criteo_impression_row_id_seq') FROM raw_criteo_impression LIMIT 1",
    "SELECT pg_read_file('postgresql.conf') FROM raw_criteo_impression LIMIT 1",
    'SELECT pg_sleep(1) FROM raw_criteo_impression LIMIT 1',
    'SELECT pg_catalog.pg_sleep(1) FROM raw_criteo_impression LIMIT 1',
    'SELECT * FROM generate_series(1,1000) LIMIT 1',
    "SELECT 'x'::regclass FROM raw_criteo_impression LIMIT 1",
    'SELECT campaign AS same, click AS same FROM raw_criteo_impression LIMIT 1',
    'WITH RECURSIVE x AS (SELECT campaign FROM raw_criteo_impression) SELECT * FROM x LIMIT 1',
    'SELECT 1 LIMIT 1',
    'SELECT cost OPERATOR(public.+) cost FROM raw_criteo_impression LIMIT 1',
]


class SQLToolsTest(unittest.TestCase):
    def test_catalog_is_live(self):
        result = schema_search('campaign、click', 'raw_criteo_impression')
        columns = result['tables']['raw_criteo_impression']
        self.assertEqual({c['column_name']: c['data_type'] for c in columns},
                         {'campaign': 'bigint', 'click': 'smallint'})
        self.assertTrue(all(c['metadata_source']=='information_schema.columns' for c in columns))
        self.assertFalse(schema_search('ad_id', 'raw_criteo_impression')['found'])

    def test_valid_cte_alias_aggregate_subquery_union(self):
        valid = [
            'SELECT * FROM public.ads_campaign_daily ORDER BY campaign_id LIMIT 10',
            'SELECT campaign,SUM(click) AS clicks FROM raw_criteo_impression GROUP BY campaign LIMIT 10',
            'WITH x AS (SELECT campaign,SUM(click) AS clicks FROM raw_criteo_impression GROUP BY campaign) SELECT * FROM x LIMIT 10',
            'SELECT a.campaign FROM raw_criteo_impression a WHERE a.click=(SELECT MAX(b.click) FROM raw_criteo_impression b) LIMIT 1',
            'SELECT campaign FROM raw_criteo_impression UNION SELECT campaign_id FROM ads_campaign_daily LIMIT 10',
            'SELECT COUNT(DISTINCT conversion_id) FILTER (WHERE conversion=1 AND conversion_id<>-1) AS conversions FROM raw_criteo_impression LIMIT 1',
        ]
        for query in valid:
            with self.subTest(query=query):
                result = sql_validate(query)
                self.assertTrue(result['valid'], result)

    def test_reject_unsafe_queries(self):
        for query in BAD_SQL:
            with self.subTest(query=query):
                self.assertFalse(sql_validate(query)['valid'], query)

    def test_executor_revalidates_without_prior_validation(self):
        self.assertFalse(sql_execute('SELECT ad_id FROM raw_criteo_impression LIMIT 1')['ok'])
        self.assertFalse(sql_execute('DELETE FROM raw_criteo_impression')['ok'])

    def test_reader_has_no_write_privilege_even_if_transaction_changed(self):
        engine = get_readonly_engine()
        try:
            with engine.connect() as conn:
                tx = conn.begin()
                try:
                    conn.exec_driver_sql('SET TRANSACTION READ WRITE')
                    with self.assertRaises(DBAPIError) as caught:
                        conn.exec_driver_sql('UPDATE public.raw_criteo_impression SET click=click WHERE FALSE')
                    self.assertEqual(caught.exception.orig.sqlstate, '42501')
                finally:
                    tx.rollback()
        finally:
            engine.dispose()

    def test_bounded_real_result_and_analysis(self):
        result = sql_execute('SELECT campaign_id,impressions,clicks,ctr FROM ads_campaign_daily ORDER BY campaign_id LIMIT 5')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['returned_rows'],5)
        self.assertEqual(result['database_user'],'criteo_reader')
        analysis = result_analyze(result['result_id'], 5)
        self.assertEqual(analysis['records'],result['rows'])
        self.assertIn('真实只读 SQL',analysis['agent_context'])
        for row in result['rows']:
            self.assertGreaterEqual(int(row['impressions']),int(row['clicks']))
        with self.assertRaises(ValueError):
            result_analyze('../connection.json')

    def test_result_size_is_bounded(self):
        sql = "SELECT '" + '汉'*4000 + "' AS payload FROM raw_criteo_impression LIMIT 100"
        result = sql_execute(sql)
        self.assertFalse(result['ok'])
        self.assertIn('1 MB',result['error'])

    def test_actual_database_statement_timeout(self):
        start = time.monotonic()
        result = sql_execute('SELECT COUNT(*) AS n FROM raw_criteo_impression a CROSS JOIN raw_criteo_impression b LIMIT 1')
        elapsed = time.monotonic()-start
        self.assertFalse(result['ok'])
        self.assertEqual(result['sqlstate'],'57014', result)
        self.assertLess(elapsed, 12)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SQLToolsTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'verified_at':datetime.now(timezone.utc).isoformat(),
              'passed':result.wasSuccessful(),'test_methods':result.testsRun,
              'unsafe_sql_cases':len(BAD_SQL),'failures':len(result.failures),
              'errors':len(result.errors),'external_llm_calls':0}
    (ROOT/'ad_agent/sql_tool_test_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
