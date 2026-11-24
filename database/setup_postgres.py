"""Initialize the project's private PostgreSQL cluster without a system service."""
import json
import os
from pathlib import Path
import secrets
import subprocess

import psycopg
from psycopg import sql
from postgres_paths import postgres_root

ROOT = Path(__file__).resolve().parents[1]
PG_ROOT = postgres_root()
BIN = PG_ROOT / '.runtime/postgresql/pgsql/bin'
DATA = PG_ROOT / 'database/pgdata'
LOGS = PG_ROOT / 'database/logs'
SECRET = PG_ROOT / 'database/.secrets/postgres.password'
CONFIG = ROOT / 'database/connection.json'


def run(*args, check=True):
    # A server child may inherit stdout handles from pg_ctl; use a file rather
    # than capture_output pipes so waiting does not block until server shutdown.
    log_path = ROOT / 'database/logs/setup.log'
    with log_path.open('ab') as log:
        result = subprocess.run([str(a) for a in args], stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    if check and result.returncode:
        print(log_path.read_bytes()[-12000:].decode('mbcs', errors='replace'))
        raise RuntimeError(f'{Path(args[0]).name} exited with code {result.returncode}')
    return result


def main():
    os.environ['TEMP'] = os.environ['TMP'] = str(ROOT / '.tmp')
    if not (BIN / 'initdb.exe').exists():
        raise RuntimeError('Extract PostgreSQL binaries into .runtime/postgresql first.')
    SECRET.parent.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    if not SECRET.exists():
        SECRET.write_text(secrets.token_urlsafe(32) + '\n', encoding='utf-8')
    admin_password = SECRET.read_text(encoding='utf-8').strip()
    if not (DATA / 'PG_VERSION').exists():
        run(BIN / 'initdb.exe', '-D', DATA, '-U', 'postgres', '--pwfile', SECRET,
            '--encoding=UTF8', '--locale=C', '--auth-host=scram-sha-256',
            '--auth-local=scram-sha-256')
        with (DATA / 'postgresql.conf').open('a', encoding='utf-8') as f:
            f.write("\n# Project-local settings\nlisten_addresses = '127.0.0.1'\nport = 5432\n"
                    "password_encryption = 'scram-sha-256'\nshared_buffers = '64MB'\n"
                    "max_connections = 30\n")
    if run(BIN / 'pg_ctl.exe', 'status', '-D', DATA, check=False).returncode != 0:
        run(BIN / 'pg_ctl.exe', 'start', '-D', DATA, '-l', LOGS / 'postgresql.log', '-w', '-t', '30')
    if CONFIG.exists():
        config = json.loads(CONFIG.read_text(encoding='utf-8'))
    else:
        config = dict(host='127.0.0.1', port=5432, dbname='criteo_ads',
                      user='criteo_app', password=secrets.token_urlsafe(32))
        CONFIG.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    with psycopg.connect(host=config['host'], port=config['port'], dbname='postgres',
                         user='postgres', password=admin_password, autocommit=True) as conn:
        if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (config['user'],)).fetchone():
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(
                sql.Identifier(config['user']), sql.Literal(config['password'])))
        if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (config['dbname'],)).fetchone():
            conn.execute(sql.SQL('CREATE DATABASE {} OWNER {} ENCODING {} TEMPLATE template0').format(
                sql.Identifier(config['dbname']), sql.Identifier(config['user']), sql.Literal('UTF8')))
    with psycopg.connect(**config) as conn:
        version = conn.execute('SHOW server_version').fetchone()[0]
    print(f"PostgreSQL {version} ready: {config['host']}:{config['port']}/{config['dbname']}")
    print('Credentials saved in database/connection.json (gitignored).')


if __name__ == '__main__':
    main()
