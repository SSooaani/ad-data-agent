"""Verified, bounded-memory full import with transactional publication and sample backup.

The Agent reader is never used here. Loading and verification happen on a private
staging table; the existing table, sequence, permissions and dependent view keep
their identities when the verified data is published.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import gzip
import hashlib
from io import BytesIO
from itertools import islice
import json
import math
from pathlib import Path
import struct
import sys
import time
import uuid
import re
import warnings

import numpy as np
import pandas as pd
from psycopg import sql as psql
from sqlalchemy import text

from db import ROOT, get_engine
from import_sample import COLUMNS, DTYPES, EXPECTED_SQL_TYPES

warnings.filterwarnings('ignore', message="The 'float_precision' argument is deprecated.*")

CHUNK_ROWS = 100_000
RAW = 'raw_criteo_impression'
VIEW = 'ads_campaign_daily'
PROGRESS = ROOT / '.tmp/full_import_progress.json'
REPORT = ROOT / 'database/full_import_report.json'
HEADER = b'PGCOPY\n\xff\r\n\x00' + struct.pack('!ii', 0, 0)
TRAILER = struct.pack('!h', -1)
FIELDS = ['row_id', *COLUMNS]


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def save_json(path, value):
    staged = path.with_name(path.name + '.part')
    staged.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    staged.replace(path)


def log(state, phase, **extra):
    state.update(phase=phase, updated_at=now(), **extra)
    save_json(PROGRESS, state)
    print(json.dumps({'phase': phase, **extra}, ensure_ascii=False), flush=True)


def table_binary_sha256(conn, table):
    query = psql.SQL('COPY (SELECT {} FROM public.{} ORDER BY row_id) TO STDOUT WITH (FORMAT BINARY)').format(
        psql.SQL(',').join(map(psql.Identifier, FIELDS)), psql.Identifier(table))
    digest = hashlib.sha256()
    with conn.connection.driver_connection.cursor() as cursor:
        with cursor.copy(query) as copy:
            for block in copy:
                digest.update(block)
    return digest.hexdigest()


def hash_source_batch(digest, frame, offset):
    # Encode the exact PostgreSQL binary COPY representation without per-row
    # Python loops. This verifies all 23 fields, including source row order.
    dtype = [('column_count', '>i2')]
    widths = {}
    for name in FIELDS:
        sql_type = EXPECTED_SQL_TYPES[name]
        code = {'int8': '>i8', 'int4': '>i4', 'int2': '>i2', 'float8': '>f8'}[sql_type]
        dtype.extend([(f'length_{name}', '>i4'), (name, code)])
        widths[name] = np.dtype(code).itemsize
    records = np.empty(len(frame), dtype=np.dtype(dtype, align=False))
    records['column_count'] = len(FIELDS)
    for name in FIELDS:
        records[f'length_{name}'] = widths[name]
        records[name] = np.arange(offset + 1, offset + len(frame) + 1, dtype=np.int64) if name == 'row_id' else frame[name].to_numpy()
    digest.update(records.tobytes())


def basic_stats(conn, table):
    return dict(conn.execute(text(f'''
        SELECT COUNT(*) AS rows, MIN(row_id) AS min_row_id, MAX(row_id) AS max_row_id,
               MIN(timestamp) AS min_timestamp, MAX(timestamp) AS max_timestamp,
               COUNT(DISTINCT campaign) AS campaigns,
               COUNT(DISTINCT FLOOR(timestamp / 86400.0)::INTEGER + 1) AS data_days,
               MIN(FLOOR(timestamp / 86400.0)::INTEGER + 1) AS first_data_day,
               MAX(FLOOR(timestamp / 86400.0)::INTEGER + 1) AS last_data_day,
               SUM(click) AS clicks, SUM(conversion) AS conversion_positive_impressions,
               SUM(attribution) AS attribution_positive_impressions, SUM(cost) AS transformed_cost_total
        FROM public."{table}"
    ''')).mappings().one())


def publish_verified(conn, state, started):
    rows = state['expected_rows']
    stage = state['staging_table']
    backup = state['backup_table']
    old_stats = state['previous_sample_stats']
    old_hash = state['previous_sample_binary_sha256']
    source_hash = state['source_sha256']
    source_binary_hash = state['source_binary_sha256']
    staging_hash = source_binary_hash
    staging_stats = state['staging_stats']
    total_clicks = staging_stats['clicks']
    staged_parquet = ROOT / '.tmp/campaign_daily.full.parquet'
    with conn.begin():
        raw_oid = conn.execute(text("SELECT 'public.raw_criteo_impression'::regclass::oid")).scalar_one()
        view_oid = conn.execute(text("SELECT 'public.ads_campaign_daily'::regclass::oid")).scalar_one()
    log(state, 'publishing_transaction', staging_stats=staging_stats)
    with conn.begin():
        conn.exec_driver_sql('LOCK TABLE public.raw_criteo_impression IN ACCESS EXCLUSIVE MODE')
        if table_binary_sha256(conn, RAW) != old_hash:
            raise RuntimeError('Original data changed while staging was loaded; refusing to overwrite it.')
        conn.exec_driver_sql(f'CREATE TABLE public."{backup}" AS TABLE public.raw_criteo_impression')
        conn.exec_driver_sql('TRUNCATE TABLE public.raw_criteo_impression RESTART IDENTITY')
        names = ','.join(f'"{name}"' for name in FIELDS)
        conn.exec_driver_sql(f'INSERT INTO public.raw_criteo_impression ({names}) SELECT {names} FROM public."{stage}" ORDER BY row_id')
        conn.exec_driver_sql(f'ALTER SEQUENCE public.raw_criteo_impression_row_id_seq RESTART WITH {rows + 1}')
        if table_binary_sha256(conn, RAW) != source_binary_hash:
            raise RuntimeError('Published table binary hash differs from the source; rolling back.')
        if conn.execute(text("SELECT 'public.raw_criteo_impression'::regclass::oid")).scalar_one() != raw_oid:
            raise RuntimeError('Original table identity changed.')
        conn.exec_driver_sql("COMMENT ON TABLE public.raw_criteo_impression IS 'Full official Criteo attribution dataset: 16468027 impressions, 22 original fields plus locally generated row_id; transformed cost is not real currency.'")
        conn.exec_driver_sql('ANALYZE public.raw_criteo_impression')
        log(state, 'refreshing_daily_view')
        conn.exec_driver_sql('REFRESH MATERIALIZED VIEW public.ads_campaign_daily')
        if conn.execute(text("SELECT 'public.ads_campaign_daily'::regclass::oid")).scalar_one() != view_oid:
            raise RuntimeError('Materialized view identity changed.')
        daily = pd.read_sql_query(text('SELECT * FROM public.ads_campaign_daily ORDER BY data_day,campaign_id'), conn)
        if int(daily.impressions.sum()) != rows or int(daily.clicks.sum()) != total_clicks:
            raise RuntimeError('Daily aggregation totals do not match the complete source.')
        if daily.duplicated(['data_day', 'campaign_id']).any() or not (daily.attributed_conversions <= daily.unique_conversions).all():
            raise RuntimeError('Daily aggregation keys or conversion counts are invalid.')
        expected_ctr = np.array([float((Decimal(int(clicks)) / Decimal(int(impressions))).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)) for clicks, impressions in zip(daily.clicks, daily.impressions)])
        if not np.allclose(daily.ctr.astype(float), expected_ctr, atol=0.0000005, rtol=0):
            raise RuntimeError('Daily CTR mismatch.')
        if not math.isclose(float(daily.transformed_cost_total.sum()), staging_stats['transformed_cost_total'], rel_tol=1e-9, abs_tol=1e-7):
            raise RuntimeError('Daily transformed-cost sum mismatch.')
        daily.to_parquet(staged_parquet, index=False, engine='pyarrow')
        pd.testing.assert_frame_equal(daily, pd.read_parquet(staged_parquet), check_exact=True)
    # At this point raw data and the view were committed atomically.
    log(state, 'database_committed', rows=rows, daily_rows=len(daily))
    target = ROOT / 'data/processed/campaign_daily.parquet'
    staged_parquet.replace(target)
    with conn.begin():
        # Drop only this import's verified staging table, never CASCADE.
        conn.exec_driver_sql(f'DROP TABLE public."{stage}"')
    report = {
        **state, 'completed_at': now(), 'phase': 'complete',
        'elapsed_seconds': round((datetime.now(timezone(timedelta(hours=8))) - datetime.fromisoformat(state['started_at'])).total_seconds(), 2),
        'source_sha256': source_hash, 'source_binary_sha256': source_binary_hash,
        'staging_binary_sha256': staging_hash, 'published_binary_sha256': source_binary_hash,
        'all_23_columns_and_row_order_verified': True,
        'gzip_crc_valid': True, 'statistics': staging_stats,
        'daily_rows': len(daily), 'daily_parquet': target.relative_to(ROOT).as_posix(),
        'daily_parquet_bytes': target.stat().st_size,
        'table_and_view_oids_preserved': True, 'backup_table': f'public.{backup}',
        'backup_rows': old_stats['rows'], 'reader_permissions_preserved': True,
        'sample_parquet_unchanged': 'data/interim/criteo_sample.parquet',
    }
    save_json(REPORT, report)
    log(state, 'complete', report='database/full_import_report.json')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def main():
    started = time.monotonic()
    source = ROOT / 'data/raw/criteo_attribution_dataset.tsv.gz'
    manifest = json.loads((ROOT / 'knowledge/dataset_manifest.json').read_text(encoding='utf-8'))
    expected_rows = manifest['rows_excluding_header']
    state = dict(started_at=now(), source=source.relative_to(ROOT).as_posix(),
                 expected_rows=expected_rows, chunk_rows=CHUNK_ROWS)
    log(state, 'checking_source')
    stat = source.stat()
    with source.open('rb') as stream:
        source_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    if source_hash != manifest['sha256']:
        raise RuntimeError('Raw source SHA-256 does not match the official verified manifest.')
    state['source_sha256'] = source_hash
    engine = get_engine()
    stage = 'criteo_full_stage_' + uuid.uuid4().hex[:12]
    backup = 'criteo_sample_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S')
    staged_parquet = ROOT / '.tmp/campaign_daily.full.parquet'
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql('SET statement_timeout = 0')
            conn.exec_driver_sql("SET lock_timeout = '10s'")
            locked = conn.execute(text("SELECT pg_try_advisory_lock(hashtext('criteo_verified_full_import'))")).scalar_one()
            conn.commit()
            if not locked:
                raise RuntimeError('Another full import is running.')
            try:
                with conn.begin():
                    types = conn.execute(text("SELECT column_name,udt_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:name ORDER BY ordinal_position"), {'name': RAW}).all()
                    if list(types) != list(EXPECTED_SQL_TYPES.items()):
                        raise RuntimeError('Original table schema differs from the verified 23-column schema.')
                    if conn.execute(text("SELECT COUNT(*) FROM pg_trigger WHERE tgrelid='public.raw_criteo_impression'::regclass AND NOT tgisinternal")).scalar_one():
                        raise RuntimeError('Unexpected insert triggers on the raw table; refusing to publish.')
                    if conn.execute(text("SELECT COUNT(*) FROM pg_constraint WHERE confrelid='public.raw_criteo_impression'::regclass AND contype='f'")).scalar_one():
                        raise RuntimeError('Foreign-key dependents require a separate migration plan.')
                    old_stats = basic_stats(conn, RAW)
                    if old_stats['rows'] == expected_rows and REPORT.exists():
                        prior = json.loads(REPORT.read_text(encoding='utf-8'))
                        if prior['source_sha256'] == source_hash and table_binary_sha256(conn, RAW) == prior['source_binary_sha256']:
                            print('Full import already present and byte-verified; no data changed.', flush=True)
                            return
                    if old_stats['rows'] != 200_000:
                        raise RuntimeError(f"Expected the known 200000-row sample, found {old_stats['rows']}; original data left unchanged.")
                    old_hash = table_binary_sha256(conn, RAW)
                    raw_oid = conn.execute(text("SELECT 'public.raw_criteo_impression'::regclass::oid")).scalar_one()
                    view_oid = conn.execute(text("SELECT 'public.ads_campaign_daily'::regclass::oid")).scalar_one()
                    ddl = (ROOT / 'database/schema.sql').read_text(encoding='utf-8').split(';', 1)[0]
                    ddl = ddl.replace('CREATE TABLE IF NOT EXISTS', 'CREATE TABLE').replace('public.raw_criteo_impression', f'public."{stage}"')
                    conn.exec_driver_sql(ddl)
                state.update(staging_table=stage, backup_table=backup, previous_sample_stats=old_stats,
                             previous_sample_binary_sha256=old_hash)
                log(state, 'loading_staging', rows=0)
                digest = hashlib.sha256(HEADER)
                rows = batches = 0
                previous_timestamp = None
                total_clicks = total_positive = total_attribution = 0
                with gzip.open(source, 'rb') as stream:
                    if stream.readline().decode('utf-8').rstrip('\r\n').split('\t') != COLUMNS:
                        raise RuntimeError('Original TSV header differs from the official 22 columns.')
                    while lines := list(islice(stream, CHUNK_ROWS)):
                        block = b''.join(lines)
                        frame = pd.read_csv(BytesIO(block), sep='\t', header=None, names=COLUMNS,
                                            dtype=DTYPES, float_precision='round_trip', on_bad_lines='error')
                        if len(frame) != len(lines) or frame.isna().any().any() or not np.isfinite(frame.to_numpy()).all():
                            raise RuntimeError(f'Invalid values or row count in source batch {batches + 1}.')
                        for name in ('click', 'conversion', 'attribution'):
                            if not frame[name].isin([0, 1]).all():
                                raise RuntimeError(f'Invalid 0/1 flag: {name}.')
                        for name in ('click_pos', 'click_nb'):
                            if not frame[name].between(np.iinfo(np.int32).min, np.iinfo(np.int32).max).all():
                                raise RuntimeError(f'INTEGER overflow: {name}.')
                        if not frame.timestamp.is_monotonic_increasing or (previous_timestamp is not None and int(frame.timestamp.iloc[0]) < previous_timestamp):
                            raise RuntimeError('Source timestamp order is invalid.')
                        previous_timestamp = int(frame.timestamp.iloc[-1])
                        hash_source_batch(digest, frame, rows)
                        with conn.begin():
                            with conn.connection.driver_connection.cursor() as cursor:
                                query = psql.SQL('COPY public.{} ({}) FROM STDIN WITH (FORMAT TEXT)').format(
                                    psql.Identifier(stage), psql.SQL(',').join(map(psql.Identifier, COLUMNS)))
                                with cursor.copy(query) as copy:
                                    copy.write(block)
                        rows += len(frame)
                        batches += 1
                        total_clicks += int(frame.click.sum())
                        total_positive += int(frame.conversion.sum())
                        total_attribution += int(frame.attribution.sum())
                        # Persist cheap progress after each committed batch, print every million.
                        state.update(rows=rows, batches=batches, updated_at=now())
                        save_json(PROGRESS, state)
                        if batches % 10 == 0 or rows == expected_rows:
                            print(f'Loaded {rows:,}/{expected_rows:,} rows ({batches} batches)', flush=True)
                digest.update(TRAILER)
                if rows != expected_rows or source.stat().st_size != stat.st_size or source.stat().st_mtime_ns != stat.st_mtime_ns:
                    raise RuntimeError('Source row count or source file changed during import.')
                source_binary_hash = digest.hexdigest()
                log(state, 'verifying_staging', rows=rows, source_binary_sha256=source_binary_hash)
                with conn.begin():
                    staging_stats = basic_stats(conn, stage)
                    if staging_stats['rows'] != rows or staging_stats['min_row_id'] != 1 or staging_stats['max_row_id'] != rows:
                        raise RuntimeError('Staging row count/record IDs differ from the source.')
                    if (staging_stats['clicks'], staging_stats['conversion_positive_impressions'], staging_stats['attribution_positive_impressions']) != (total_clicks, total_positive, total_attribution):
                        raise RuntimeError('Staging flag aggregates differ from the source.')
                    staging_hash = table_binary_sha256(conn, stage)
                    if staging_hash != source_binary_hash:
                        raise RuntimeError('Full staging binary hash differs from the source: no original data changed.')
                    conn.exec_driver_sql(f'ANALYZE public."{stage}"')
                state['staging_stats'] = staging_stats
                publish_verified(conn, state, started)
            except Exception as exc:
                conn.rollback()
                log(state, 'failed', error=str(exc)[:1000])
                raise
            finally:
                conn.rollback()
                conn.execute(text("SELECT pg_advisory_unlock(hashtext('criteo_verified_full_import'))"))
                conn.commit()
    finally:
        engine.dispose()


def resume_validated():
    started = time.monotonic()
    state = json.loads(PROGRESS.read_text(encoding='utf-8'))
    if state.get('phase') != 'failed' or not state.get('staging_stats'):
        raise RuntimeError('Resume requires a failed publication with previously validated staging statistics.')
    stage = state.get('staging_table', '')
    if not re.fullmatch(r'criteo_full_stage_[0-9a-f]{12}', stage):
        raise RuntimeError('Unexpected staging table identifier.')
    if state['expected_rows'] != 16_468_027 or state['staging_stats']['rows'] != 16_468_027:
        raise RuntimeError('Incomplete staged dataset.')
    source = ROOT / state['source']
    manifest = json.loads((ROOT / 'knowledge/dataset_manifest.json').read_text(encoding='utf-8'))
    with source.open('rb') as stream:
        current_source = hashlib.file_digest(stream, 'sha256').hexdigest()
    if current_source != state['source_sha256'] or current_source != manifest['sha256']:
        raise RuntimeError('Source changed since the validated import.')
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql('SET statement_timeout = 0')
            conn.exec_driver_sql("SET lock_timeout = '10s'")
            locked = conn.execute(text("SELECT pg_try_advisory_lock(hashtext('criteo_verified_full_import'))")).scalar_one()
            conn.commit()
            if not locked:
                raise RuntimeError('Another full import is running.')
            try:
                log(state, 'revalidating_staging_for_resume')
                with conn.begin():
                    if table_binary_sha256(conn, stage) != state['source_binary_sha256']:
                        raise RuntimeError('Staging data changed; resume refused.')
                state['previous_publish_error'] = state.pop('error', None)
                state['resumed_after_failed_publish'] = True
                publish_verified(conn, state, started)
            except Exception as exc:
                conn.rollback()
                log(state, 'failed', error=str(exc)[:1000])
                raise
            finally:
                conn.rollback()
                conn.execute(text("SELECT pg_advisory_unlock(hashtext('criteo_verified_full_import'))"))
                conn.commit()
    finally:
        engine.dispose()


if __name__ == '__main__':
    if sys.argv[1:] == ['--resume-validated']:
        resume_validated()
    elif sys.argv[1:]:
        raise SystemExit('Usage: python database/import_full.py [--resume-validated]')
    else:
        main()
