"""Actual column definitions: information_schema first, pg_catalog for materialized views."""
import re
from sqlalchemy import text

from database.readonly import get_readonly_engine

ALLOWED_TABLES = ('raw_criteo_impression', 'ads_campaign_daily')


def load_catalog(connection=None):
    if connection is None:
        engine = get_readonly_engine()
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql('SET TRANSACTION READ ONLY')
                return load_catalog(conn)
        finally:
            engine.dispose()
    rows = connection.execute(text('''
        SELECT table_name, column_name, ordinal_position AS position,
               data_type, is_nullable='NO' AS not_null,
               'information_schema.columns' AS metadata_source
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name IN (:raw,:daily)
        UNION ALL
        SELECT c.relname, a.attname, a.attnum,
               format_type(a.atttypid,a.atttypmod), a.attnotnull,
               'pg_catalog (materialized view)' AS metadata_source
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid
        WHERE n.nspname='public' AND c.relkind='m' AND c.relname IN (:raw,:daily)
          AND a.attnum>0 AND NOT a.attisdropped
          AND has_table_privilege(c.oid,'SELECT')
        ORDER BY table_name, position
    '''), {'raw': ALLOWED_TABLES[0], 'daily': ALLOWED_TABLES[1]}).mappings().all()
    result = {}
    for row in rows:
        result.setdefault(row['table_name'], []).append(dict(row))
    if set(result) != set(ALLOWED_TABLES):
        raise RuntimeError('Allowed relations are missing or reader privileges are incomplete.')
    return result


def schema_search(query='', table_name=None):
    catalog = load_catalog()
    if table_name:
        table_name = table_name.removeprefix('public.')
    tokens = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', query)
    inferred = [token for token in tokens if token in ALLOWED_TABLES]
    selected = table_name or (inferred[0] if len(inferred) == 1 else None)
    fields = [token for token in tokens if token not in ALLOWED_TABLES and token != 'public']
    if selected and selected not in ALLOWED_TABLES:
        return {'found': False, 'tables': {}, 'missing_table': selected, 'missing_fields': fields}
    tables = {name: [row for row in columns if not fields or row['column_name'] in fields]
              for name, columns in catalog.items() if not selected or name == selected}
    found_fields = {column['column_name'] for columns in tables.values() for column in columns}
    return {'found': any(tables.values()), 'schema': 'public', 'tables': tables,
            'missing_fields': [field for field in fields if field not in found_fields],
            'source': 'live PostgreSQL information_schema; pg_catalog fallback for materialized views'}
