import json
from pathlib import Path

from sqlalchemy import URL, create_engine
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
READER = 'criteo_reader'


def get_readonly_engine():
    path = ROOT / 'database/readonly_connection.json'
    if not path.exists():
        raise RuntimeError('Initialize read-only credentials: python database/setup_readonly.py')
    config = json.loads(path.read_text(encoding='utf-8'))
    if config['user'] != READER:
        raise RuntimeError('Query tools require the dedicated criteo_reader account.')
    url = URL.create('postgresql+psycopg', username=config['user'], password=config['password'],
                     host=config['host'], port=config['port'], database=config['dbname'])
    return create_engine(url, poolclass=NullPool, echo=False, connect_args={
        'connect_timeout': 5,
        'options': '-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000 -c search_path=pg_catalog',
    })
