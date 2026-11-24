"""Bounded read-only execution and analysis of persisted, genuine query results."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
import re
import uuid

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlglot.errors import SqlglotError

from database.readonly import READER, ROOT, get_readonly_engine
from .sql_policy import TIMEOUT_MS, checked_query

RESULTS = ROOT / '.tmp/sql_results'
MAX_RESULT_BYTES = 1_000_000


def json_value(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value) if value.is_finite() else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise ValueError(f'Unsupported result value type: {type(value).__name__}')


def sql_execute(sql):
    engine = get_readonly_engine()
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                conn.exec_driver_sql(f"SET LOCAL statement_timeout = '{TIMEOUT_MS}ms'")
                conn.exec_driver_sql("SET LOCAL lock_timeout = '1000ms'")
                proof = conn.execute(text('''
                    SELECT current_user, current_setting('transaction_read_only'),
                           rolsuper, rolcreatedb, rolcreaterole
                    FROM pg_roles WHERE rolname=current_user
                ''')).one()
                if tuple(proof) != (READER, 'on', False, False, False):
                    raise RuntimeError('Dedicated reader and read-only transaction are required.')
                # Revalidate against the live schema in the read-only transaction.
                validation = checked_query(sql, conn)
                result = conn.execution_options(stream_results=True, max_row_buffer=100).exec_driver_sql(validation['safe_sql'])
                columns = list(result.keys())
                rows, size = [], 0
                for row in result.fetchmany(validation['row_limit'] + 1):
                    if len(rows) >= validation['row_limit']:
                        raise RuntimeError('Database returned more rows than the validated LIMIT.')
                    record = {column: json_value(value) for column, value in zip(columns, row)}
                    size += len(json.dumps(record, ensure_ascii=False).encode('utf-8'))
                    if size > MAX_RESULT_BYTES:
                        raise ValueError('Result exceeds 1 MB; select fewer columns or rows.')
                    rows.append(record)
                result.close()
        result_id = uuid.uuid4().hex
        payload = {
            'ok': True, 'result_id': result_id, 'sql': validation['safe_sql'],
            'database_user': READER, 'read_only': True, 'columns': columns,
            'rows': rows, 'returned_rows': len(rows), 'row_limit': validation['row_limit'],
            'limit_reached': len(rows) == validation['row_limit'],
            'statement_timeout_ms': TIMEOUT_MS,
            'executed_at': datetime.now(timezone.utc).isoformat(),
            'numeric_encoding': 'PostgreSQL NUMERIC values are exact decimal strings; FLOAT8 values are JSON numbers.',
        }
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / f'{result_id}.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        # Retain the 32 most recent query results.
        owned = sorted((p for p in RESULTS.glob('*.json') if re.fullmatch(r'[a-f0-9]{32}', p.stem)),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for old in owned[32:]:
            old.unlink()
        return payload
    except DBAPIError as exc:
        code = getattr(exc.orig, 'sqlstate', None)
        return {'ok': False, 'error': 'Query timed out or was cancelled.' if code == '57014'
                else str(exc.orig)[:500], 'sqlstate': code, 'rows': []}
    except (ValueError, SqlglotError, RecursionError) as exc:
        return {'ok': False, 'error': str(exc)[:1000], 'rows': []}
    finally:
        engine.dispose()


def result_analyze(result_id, preview_rows=20):
    if not re.fullmatch(r'[a-f0-9]{32}', result_id):
        raise ValueError('Use the result_id returned by sql_execute, not a filename or invented records.')
    if not 1 <= preview_rows <= 100:
        raise ValueError('preview_rows must be between 1 and 100.')
    path = RESULTS / f'{result_id}.json'
    if not path.is_file():
        raise ValueError('Result not found or evicted; execute the query again.')
    result = json.loads(path.read_text(encoding='utf-8'))
    if (datetime.now(timezone.utc) - datetime.fromisoformat(result['executed_at'])).total_seconds() > 86400:
        raise ValueError('Result is older than 24 hours; execute the query again.')
    rows = result['rows']
    summaries = {}
    for column in result['columns']:
        nonnull = [row[column] for row in rows if row[column] is not None]
        entry = {'nulls': sum(row[column] is None for row in rows)}
        try:
            numbers = [Decimal(str(value)) for value in nonnull if not isinstance(value, bool)]
            if numbers and len(numbers) == len(nonnull) and all(value.is_finite() for value in numbers):
                entry.update(min=str(min(numbers)), max=str(max(numbers)))
        except InvalidOperation:
            pass
        summaries[column] = entry
    warnings = ['Only returned SQL rows are analyzed; these are not necessarily all matching rows.',
                'Per-group distinct conversions must not be summed into a global distinct count.',
                'cost/cpo and transformed_cost_total are transformed values, not real currency; real ROAS is unavailable.']
    if result['limit_reached']:
        warnings.append('The SQL LIMIT was reached; more matching rows may exist.')
    analysis = {
        'result_id': result_id, 'sql': result['sql'], 'executed_at': result['executed_at'],
        'returned_rows': len(rows), 'preview_rows': min(preview_rows, len(rows)),
        'records': rows[:preview_rows], 'column_summaries': summaries,
        'warnings': warnings, 'numeric_encoding': result['numeric_encoding'],
    }
    context = '����������ʵֻ�� SQL ��ѯ������ͣ����� warnings��������������ݻ����롣\n'
    context += json.dumps(analysis, ensure_ascii=False, separators=(',', ':'))
    return {**analysis, 'agent_context': context}
