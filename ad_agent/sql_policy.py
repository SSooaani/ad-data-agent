"""Fail-closed SQLGlot policy for bounded SELECT queries on live allowlisted schemas."""
import re

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope

from .catalog import ALLOWED_TABLES, load_catalog

MAX_ROWS = 1000
TIMEOUT_MS = 5000
MAX_SQL_CHARS = 12000
SAFE_FUNCTIONS = {
    'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'ROUND', 'FLOOR', 'CEIL', 'ABS',
    'NULLIF', 'COALESCE', 'CAST', 'CASE', 'IF', 'GREATEST', 'LEAST',
    'ROW_NUMBER', 'RANK', 'DENSE_RANK', 'LAG', 'LEAD',
    'LOWER', 'UPPER', 'LENGTH', 'TRIM',
    'AND', 'OR', 'EXISTS',
}
SAFE_TYPES = {
    'SMALLINT', 'INT', 'BIGINT', 'FLOAT', 'DOUBLE', 'DECIMAL', 'BOOLEAN',
    'TEXT', 'VARCHAR', 'CHAR', 'DATE', 'TIMESTAMP', 'TIMESTAMPTZ', 'INTERVAL',
}
QUERY_TYPES = (exp.Select, exp.Union, exp.Intersect, exp.Except)


def _literal_int(node, label, minimum, maximum):
    if not isinstance(node, exp.Literal) or node.is_string or not re.fullmatch(r'\d+', node.this):
        raise ValueError(f'{label} must be a literal integer.')
    value = int(node.this)
    if not minimum <= value <= maximum:
        raise ValueError(f'{label} must be between {minimum} and {maximum}.')
    return value


def checked_query(sql, connection=None):
    if not isinstance(sql, str) or not sql.strip() or len(sql) > MAX_SQL_CHARS:
        raise ValueError(f'SQL must contain 1-{MAX_SQL_CHARS} characters.')
    parsed = sqlglot.parse(sql, read='postgres', error_level=sqlglot.ErrorLevel.RAISE)
    if len(parsed) != 1 or parsed[0] is None:
        raise ValueError('Exactly one SELECT statement is required.')
    tree = normalize_identifiers(parsed[0], dialect='postgres')
    if not isinstance(tree, QUERY_TYPES):
        raise ValueError('Only SELECT queries, including SELECT CTEs/set operations, are allowed.')
    nodes = list(tree.walk())
    if len(nodes) > 2500:
        raise ValueError('SQL expression is too complex.')
    forbidden = (exp.DDL, exp.DML, exp.Command, exp.Into, exp.Lock, exp.Dot, exp.Operator,
                 exp.Parameter, exp.Placeholder)
    for node in nodes:
        if isinstance(node, forbidden):
            raise ValueError(f'Forbidden SQL construct: {type(node).__name__}.')
        if isinstance(node, exp.With) and node.args.get('recursive'):
            raise ValueError('Recursive CTEs are not allowed.')
        if isinstance(node, exp.Select) and (node.args.get('into') or node.args.get('locks')):
            raise ValueError('SELECT INTO and row locks are not allowed.')
        if isinstance(node, exp.Func):
            if isinstance(node, exp.Anonymous) or node.sql_name() not in SAFE_FUNCTIONS:
                raise ValueError(f'Function is not allowlisted: {node.sql_name()}.')
        if isinstance(node, exp.DataType) and getattr(node.this, 'value', node.this) not in SAFE_TYPES:
            raise ValueError('Only built-in allowlisted scalar casts are supported.')
    limit = tree.args.get('limit')
    if not isinstance(limit, exp.Limit) or limit.args.get('limit_options'):
        raise ValueError(f'An outer LIMIT between 1 and {MAX_ROWS} is required.')
    row_limit = _literal_int(limit.expression, 'LIMIT', 1, MAX_ROWS)
    offset = tree.args.get('offset')
    if offset:
        _literal_int(offset.expression, 'OFFSET', 0, 100000)
    tables = set()
    for scope in traverse_scope(tree):
        if not isinstance(scope.expression, QUERY_TYPES):
            raise ValueError('Only SELECT-based sources are supported.')
        for _, (_, source) in scope.selected_sources.items():
            if isinstance(source, exp.Table):
                if not isinstance(source.this, exp.Identifier):
                    raise ValueError('Table functions are not allowed.')
                if source.catalog or source.db not in ('', 'public') or source.name not in ALLOWED_TABLES:
                    raise ValueError(f'Table is not allowlisted: {source.sql(dialect="postgres")}.')
                tables.add(source.name)
            elif not isinstance(source, Scope):
                raise ValueError('Unsupported table source.')
    if not tables:
        raise ValueError('The query must read an allowlisted project table or materialized view.')
    catalog = load_catalog(connection)
    schema = {'public': {name: {row['column_name']: row['data_type'] for row in columns}
                         for name, columns in catalog.items()}}
    qualified = qualify(tree.copy(), dialect='postgres', db='public', schema=schema,
                        validate_qualify_columns=True, allow_partial_qualification=False)
    labels = qualified.named_selects
    if len(labels) != len(set(labels)):
        raise ValueError('Output column names must be unique; assign distinct aliases.')
    # Remove comments, then serialize the checked AST, never execute the original string.
    for node in qualified.walk():
        node.pop_comments()
    return {'valid': True, 'safe_sql': qualified.sql(dialect='postgres'),
            'tables': sorted(tables), 'row_limit': row_limit,
            'statement_timeout_ms': TIMEOUT_MS, 'columns_verified_from': 'live PostgreSQL metadata'}


def sql_validate(sql):
    try:
        return checked_query(sql)
    except (sqlglot.errors.SqlglotError, ValueError, RecursionError) as exc:
        return {'valid': False, 'errors': [str(exc)[:1000]], 'max_rows': MAX_ROWS}
