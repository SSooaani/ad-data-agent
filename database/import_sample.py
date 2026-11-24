"""Import the first 200,000 impressions; fail safely instead of duplicating rows."""
import csv
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from sqlalchemy import text

from db import ROOT, get_engine

COLUMNS = [
    'timestamp', 'uid', 'campaign', 'conversion', 'conversion_timestamp',
    'conversion_id', 'attribution', 'click', 'click_pos', 'click_nb',
    'cost', 'cpo', 'time_since_last_click',
    'cat1', 'cat2', 'cat3', 'cat4', 'cat5', 'cat6', 'cat7', 'cat8', 'cat9',
]
DTYPES = {c: 'float64' if c in ('cost', 'cpo') else 'int64' for c in COLUMNS}
EXPECTED_SQL_TYPES = {'row_id': 'int8', **dict.fromkeys(COLUMNS, 'int8')}
EXPECTED_SQL_TYPES.update(conversion='int2', attribution='int2', click='int2',
                          click_pos='int4', click_nb='int4', cost='float8', cpo='float8')
SAMPLE_ROWS = 200_000


def read_sample():
    source = ROOT / 'data/raw/criteo_attribution_dataset.tsv.gz'
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    official = json.loads((ROOT / 'knowledge/dataset_manifest.json').read_text(encoding='utf-8'))
    if digest != official['sha256']:
        raise ValueError('Source dataset differs from its verified manifest.')
    with gzip.open(source, 'rt', encoding='utf-8', newline='') as stream:
        reader = csv.reader(stream, delimiter='\t')
        first = next(reader)
        if len(first) != 22:
            raise ValueError(f'Expected 22 columns, found {len(first)}.')
        has_header = first == COLUMNS
        first_data = next(reader) if has_header else first
        if len(first_data) != 22:
            raise ValueError('First data row does not have 22 fields.')
        # Also rejects a misspelled/reordered header instead of treating it as data.
        for column, value in zip(COLUMNS, first_data):
            (float if column in ('cost', 'cpo') else int)(value)
    df = pd.read_csv(source, sep='\t', compression='gzip',
                     header=0 if has_header else None, names=COLUMNS,
                     dtype=DTYPES, nrows=SAMPLE_ROWS, on_bad_lines='error')
    if len(df) != SAMPLE_ROWS or list(df.columns) != COLUMNS:
        raise ValueError('Unexpected sample size or columns.')
    if df.isna().any().any() or not np.isfinite(df.to_numpy()).all():
        raise ValueError('Null or non-finite values in source sample.')
    for field in ('conversion', 'click', 'attribution'):
        if not df[field].isin([0, 1]).all():
            raise ValueError(f'Invalid binary flag: {field}')
    if not df['timestamp'].is_monotonic_increasing:
        raise ValueError('Source timestamps are not sorted.')
    return df, digest, has_header, first_data


def main():
    df, digest, has_header, first_data = read_sample()
    staged_parquet = ROOT / '.tmp/criteo_sample.parquet'
    df.to_parquet(staged_parquet, index=False, engine='pyarrow')
    assert_frame_equal(df, pd.read_parquet(staged_parquet), check_exact=True)
    engine = get_engine()
    quoted_columns = ', '.join(f'"{c}"' for c in COLUMNS)
    with engine.begin() as conn:
        conn.exec_driver_sql((ROOT / 'database/schema.sql').read_text(encoding='utf-8'))
        actual = conn.execute(text("""
            SELECT column_name, udt_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='raw_criteo_impression'
            ORDER BY ordinal_position
        """)).all()
        if list(actual) != list(EXPECTED_SQL_TYPES.items()):
            raise RuntimeError(f'Existing table has an unexpected schema: {actual}')
        conn.exec_driver_sql('LOCK TABLE public.raw_criteo_impression IN EXCLUSIVE MODE')
        before = conn.execute(text('SELECT COUNT(*) FROM public.raw_criteo_impression')).scalar_one()
        if before == 0:
            df.to_sql('raw_criteo_impression', conn, schema='public', if_exists='append',
                      index=False, chunksize=1000)
            action = 'inserted'
        elif before == SAMPLE_ROWS:
            action = 'already_present_verified_no_append'
        else:
            raise RuntimeError(f'Table already has {before} rows. Refusing to append or overwrite.')
        stored = pd.read_sql_query(text(
            f'SELECT {quoted_columns} FROM public.raw_criteo_impression ORDER BY row_id'), conn)
        # Full row-and-field comparison, not just matching row counts.
        assert_frame_equal(df, stored, check_exact=True)
        stats = dict(conn.execute(text('''
            SELECT COUNT(*) AS rows, COUNT(DISTINCT row_id) AS distinct_row_ids,
                   MIN(row_id) AS min_row_id, MAX(row_id) AS max_row_id,
                   MIN(timestamp) AS min_timestamp, MAX(timestamp) AS max_timestamp,
                   COUNT(DISTINCT campaign) AS campaigns,
                   SUM(click) AS clicked_impressions,
                   SUM(conversion) AS conversion_positive_impressions,
                   COUNT(DISTINCT conversion_id) FILTER
                       (WHERE conversion=1 AND conversion_id <> -1) AS distinct_conversion_ids,
                   SUM(attribution) AS attribution_positive_impressions
            FROM public.raw_criteo_impression
        ''')).mappings().one())
    target = ROOT / 'data/interim/criteo_sample.parquet'
    staged_parquet.replace(target)
    assert_frame_equal(df, pd.read_parquet(target), check_exact=True)
    report = {
        'verified_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'database': 'criteo_ads', 'table': 'public.raw_criteo_impression',
        'source_sha256': digest, 'source_has_header': has_header,
        'source_columns': COLUMNS, 'first_data_row': first_data,
        'sampling': 'first 200000 data rows in timestamp order; not random',
        'import_action': action, 'statistics': stats,
        'null_values': int(df.isna().sum().sum()),
        'negative_one_counts': {c: int(df[c].eq(-1).sum()) for c in COLUMNS if DTYPES[c] == 'int64'},
        'sql_columns_including_generated_row_id': len(actual),
        'postgres_rows_equal_source_sample': True,
        'parquet_rows_equal_source_sample': True,
        'parquet': target.relative_to(ROOT).as_posix(),
        'parquet_bytes': target.stat().st_size,
        'money_semantics': 'cost and cpo are transformed values, not real currency amounts',
    }
    (ROOT / 'database/import_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    engine.dispose()


if __name__ == '__main__':
    main()
