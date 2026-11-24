"""Provision only the Agent reader; preserve the existing import/owner account."""
import json
from pathlib import Path
import secrets
import sys

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.readonly import READER


def main():
    owner = json.loads((ROOT / 'database/connection.json').read_text(encoding='utf-8'))
    path = ROOT / 'database/readonly_connection.json'
    config = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'host': owner['host'], 'port': owner['port'], 'dbname': owner['dbname'],
        'user': READER, 'password': secrets.token_urlsafe(32),
    }
    if config['user'] != READER:
        raise RuntimeError('Unexpected read-only role in local config.')
    password = (ROOT / 'database/.secrets/postgres.password').read_text(encoding='utf-8').strip()
    with psycopg.connect(host=owner['host'], port=owner['port'], dbname=owner['dbname'],
                         user='postgres', password=password) as conn:
        exists = conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (READER,)).fetchone()
        if exists and not path.exists():
            raise RuntimeError('Reader role already exists without this project credential file.')
        if not exists:
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB '
                                 'NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 5')
                         .format(sql.Identifier(READER), sql.Literal(config['password'])))
        role = sql.Identifier(READER)
        db = sql.Identifier(owner['dbname'])
        conn.execute(sql.SQL('ALTER ROLE {} SET default_transaction_read_only = on').format(role))
        conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5s'").format(role))
        conn.execute(sql.SQL("ALTER ROLE {} SET lock_timeout = '1s'").format(role))
        conn.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '10s'").format(role))
        conn.execute(sql.SQL('ALTER ROLE {} SET search_path = pg_catalog').format(role))
        conn.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM {}').format(db, role))
        conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(db, role))
        # TEMP is inherited from PUBLIC by default; the project owner retains its own privileges.
        conn.execute(sql.SQL('REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC').format(db))
        conn.execute(sql.SQL('REVOKE CREATE ON SCHEMA public FROM {}').format(role))
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
        conn.execute(sql.SQL('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}').format(role))
        conn.execute(sql.SQL('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}').format(role))
        conn.execute(sql.SQL('GRANT SELECT ON public.raw_criteo_impression, public.ads_campaign_daily TO {}').format(role))
    path.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    with psycopg.connect(**config) as conn:
        proof = conn.execute('''
            SELECT current_user, current_setting('default_transaction_read_only'),
                   has_table_privilege(current_user,'public.raw_criteo_impression','SELECT'),
                   has_table_privilege(current_user,'public.raw_criteo_impression','INSERT,UPDATE,DELETE'),
                   has_schema_privilege(current_user,'public','CREATE'),
                   has_database_privilege(current_user,current_database(),'TEMP')
        ''').fetchone()
    if proof != (READER, 'on', True, False, False, False):
        raise RuntimeError(f'Reader permission verification failed: {proof}')
    print('criteo_reader ready: SELECT only on the two allowed relations; no writes, CREATE or TEMP.')


if __name__ == '__main__':
    main()
