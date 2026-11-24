import json
from pathlib import Path

from sqlalchemy import URL, create_engine

ROOT = Path(__file__).resolve().parents[1]


def get_engine():
    config = json.loads((ROOT / 'database/connection.json').read_text(encoding='utf-8'))
    url = URL.create(
        'postgresql+psycopg', username=config['user'], password=config['password'],
        host=config['host'], port=config['port'], database=config['dbname'],
    )
    return create_engine(url, echo=False, pool_pre_ping=True)
