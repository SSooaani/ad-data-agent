CREATE TABLE IF NOT EXISTS public.raw_criteo_impression (
    row_id BIGSERIAL PRIMARY KEY,
    timestamp BIGINT,
    uid BIGINT,
    campaign BIGINT,
    conversion SMALLINT,
    conversion_timestamp BIGINT,
    conversion_id BIGINT,
    attribution SMALLINT,
    click SMALLINT,
    click_pos INTEGER,
    click_nb INTEGER,
    cost DOUBLE PRECISION,
    cpo DOUBLE PRECISION,
    time_since_last_click BIGINT,
    cat1 BIGINT,
    cat2 BIGINT,
    cat3 BIGINT,
    cat4 BIGINT,
    cat5 BIGINT,
    cat6 BIGINT,
    cat7 BIGINT,
    cat8 BIGINT,
    cat9 BIGINT
);

COMMENT ON TABLE public.raw_criteo_impression IS
'One row per Criteo impression. Source has 22 fields; row_id is generated locally. Loaded scope is recorded in full_import_report.json or the historical sample import_report.json.';
COMMENT ON COLUMN public.raw_criteo_impression.row_id IS 'Local database record ID; not an original Criteo field.';
COMMENT ON COLUMN public.raw_criteo_impression.timestamp IS 'Relative impression timestamp in seconds, starting at 0; not a Unix calendar timestamp.';
COMMENT ON COLUMN public.raw_criteo_impression.uid IS 'Anonymized user identifier.';
COMMENT ON COLUMN public.raw_criteo_impression.campaign IS 'Original Criteo campaign identifier.';
COMMENT ON COLUMN public.raw_criteo_impression.conversion IS '0/1: conversion occurred within 30 days after this impression. Positive rows are not independent orders.';
COMMENT ON COLUMN public.raw_criteo_impression.conversion_timestamp IS 'Conversion timestamp; -1 when no conversion was observed.';
COMMENT ON COLUMN public.raw_criteo_impression.conversion_id IS 'Conversion identifier shared across related impressions; -1 when absent. Deduplicate valid IDs for distinct conversions.';
COMMENT ON COLUMN public.raw_criteo_impression.attribution IS '0/1: whether the conversion was attributed to Criteo.';
COMMENT ON COLUMN public.raw_criteo_impression.click IS '0/1: this impression was clicked; not an independent click event log.';
COMMENT ON COLUMN public.raw_criteo_impression.click_pos IS 'Position of the click before conversion; 0 is first click. Preserve original -1 sentinel.';
COMMENT ON COLUMN public.raw_criteo_impression.click_nb IS 'Number of clicks before conversion. Preserve original -1 sentinel.';
COMMENT ON COLUMN public.raw_criteo_impression.cost IS 'Transformed impression cost; not a real currency amount. Do not label sums as actual ad spend.';
COMMENT ON COLUMN public.raw_criteo_impression.cpo IS 'Transformed cost per order; not a real currency amount or actual revenue.';
COMMENT ON COLUMN public.raw_criteo_impression.time_since_last_click IS 'Seconds since last click. Preserve original -1 sentinel.';
COMMENT ON COLUMN public.raw_criteo_impression.cat1 IS 'Anonymized categorical contextual feature; business meaning undisclosed.';
COMMENT ON COLUMN public.raw_criteo_impression.cat2 IS 'Anonymized categorical contextual feature; business meaning undisclosed.';
COMMENT ON COLUMN public.raw_criteo_impression.cat3 IS 'Anonymized categorical contextual feature; business meaning undisclosed.';
COMMENT ON COLUMN public.raw_criteo_impression.cat4 IS 'Anonymized categorical contextual feature; business meaning undisclosed.';
COMMENT ON COLUMN public.raw_criteo_impression.cat5 IS 'Anonymized categorical contextual feature; business meaning undisclosed.';
COMMENT ON COLUMN public.raw_criteo_impression.cat6 IS 'Anonymized categorical contextual feature; business meaning undisclosed.';
COMMENT ON COLUMN public.raw_criteo_impression.cat7 IS 'Anonymized categorical contextual feature; business meaning undisclosed.';
COMMENT ON COLUMN public.raw_criteo_impression.cat8 IS 'Anonymized categorical contextual feature; business meaning undisclosed.';
COMMENT ON COLUMN public.raw_criteo_impression.cat9 IS 'Anonymized categorical contextual feature; business meaning undisclosed.';
