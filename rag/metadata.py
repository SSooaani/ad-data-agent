"""Live, read-only PostgreSQL catalog queries; never infer columns from vectors."""
from sqlalchemy import text
from database.readonly import get_readonly_engine

TABLES = ('raw_criteo_impression', 'ads_campaign_daily')


def database_schema(table_name=None, field_name=None):
    if table_name:
        table_name = table_name.removeprefix('public.')
    if table_name and table_name not in TABLES:
        return {'source': 'postgresql.pg_catalog', 'tables': [], 'found': False,
                'message': f'No supported database relation named {table_name}.'}
    engine = get_readonly_engine()
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql('SET TRANSACTION READ ONLY')
            conn.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
            rows = conn.execute(text('''
                SELECT c.relname AS table_name, c.relkind AS relation_kind,
                       a.attname AS field_name, a.attnum AS position,
                       format_type(a.atttypid,a.atttypmod) AS data_type,
                       a.attnotnull AS not_null,
                       col_description(c.oid,a.attnum) AS description
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                JOIN pg_attribute a ON a.attrelid=c.oid
                WHERE n.nspname='public' AND c.relname IN (:raw,:daily)
                  AND a.attnum>0 AND NOT a.attisdropped
                  AND (CAST(:table_name AS TEXT) IS NULL OR c.relname=:table_name)
                  AND (CAST(:field_name AS TEXT) IS NULL OR a.attname=:field_name)
                ORDER BY c.relname,a.attnum
            '''), dict(raw=TABLES[0], daily=TABLES[1], table_name=table_name,
                       field_name=field_name)).mappings().all()
        return {'source': 'postgresql.pg_catalog', 'found': bool(rows),
                'columns': [dict(row) for row in rows]}
    finally:
        engine.dispose()
