-- =============================================================================
-- load-parcels-remaining-counties.sql
--
-- Loads parcel data for the 16 remaining ARC counties into PostGIS.
-- Cobb County (13067) is assumed to already be loaded.
-- The following counties are excluded:
--   13035 Butts, 13143 Haralson, 13159 Jasper  (no parcel layer in RPD24_V2.gdb)
--   13077 Coweta                                (geometry/CRS issue; ~43.6% spatial assignment rate)
--
-- Prerequisites:
--   - Schema acs_5yr_2024 must exist.
--   - Table acs_5yr_2024.arc_parcels_2024 must exist (created when Cobb was loaded).
--   - Each county's raw parcel table must already be loaded via ogr2ogr, e.g.:
--
--       ogr2ogr \
--         -f PostgreSQL \
--         "PG:host=<host> port=<port> dbname=<db> user=<user>" \
--         inputs/RegionalParcelDataSet2024/RPD24_V2.gdb \
--         "RPD24_V2_<FIPS>" \
--         -nln "acs_5yr_2024.parcels_<FIPS>_raw" \
--         -nlt MULTIPOLYGON \
--         -dim XY \
--         -lco GEOMETRY_NAME=geom \
--         -lco FID=gid \
--         -lco LAUNDER=NO \
--         -overwrite
--
--     Run the above for each FIPS in:
--       13013 13015 13045 13057 13063 13085 13089 13097
--       13113 13117 13121 13135 13151 13217 13223 13247
--
-- Usage:
--   psql -h leduc.office.hbaspecto.com -d atlanta_db -U postgres \
--        -f load-parcels-remaining-counties.sql
-- =============================================================================

\set ON_ERROR_STOP on

-- -------------------------------------------------------------------------
-- 1. Ensure arc_county_map_2024 exists and is populated for all 17 counties
--    (including Cobb). Use INSERT ... ON CONFLICT DO NOTHING so re-running
--    this script is safe.
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS acs_5yr_2024.arc_county_map_2024 (
    state_fips    text NOT NULL,
    county_fips   text PRIMARY KEY,
    full_fips     text NOT NULL,
    county_name   text NOT NULL,
    source_layer  text NOT NULL,
    raw_table_name text NOT NULL
);

INSERT INTO acs_5yr_2024.arc_county_map_2024 (
    state_fips, county_fips, full_fips, county_name, source_layer, raw_table_name
)
VALUES
    ('13', '013', '13013', 'Barrow',   'RPD24_V2_13013', 'parcels_13013_raw'),
    ('13', '015', '13015', 'Bartow',   'RPD24_V2_13015', 'parcels_13015_raw'),
    ('13', '045', '13045', 'Carroll',  'RPD24_V2_13045', 'parcels_13045_raw'),
    ('13', '057', '13057', 'Cherokee', 'RPD24_V2_13057', 'parcels_13057_raw'),
    ('13', '063', '13063', 'Clayton',  'RPD24_V2_13063', 'parcels_13063_raw'),
    ('13', '067', '13067', 'Cobb',     'RPD24_V2_13067', 'parcels_13067_raw'),
    ('13', '085', '13085', 'Dawson',   'RPD24_V2_13085', 'parcels_13085_raw'),
    ('13', '089', '13089', 'DeKalb',   'RPD24_V2_13089', 'parcels_13089_raw'),
    ('13', '097', '13097', 'Douglas',  'RPD24_V2_13097', 'parcels_13097_raw'),
    ('13', '113', '13113', 'Fayette',  'RPD24_V2_13113', 'parcels_13113_raw'),
    ('13', '117', '13117', 'Forsyth',  'RPD24_V2_13117', 'parcels_13117_raw'),
    ('13', '121', '13121', 'Fulton',   'RPD24_V2_13121', 'parcels_13121_raw'),
    ('13', '135', '13135', 'Gwinnett', 'RPD24_V2_13135', 'parcels_13135_raw'),
    ('13', '151', '13151', 'Henry',    'RPD24_V2_13151', 'parcels_13151_raw'),
    ('13', '217', '13217', 'Newton',   'RPD24_V2_13217', 'parcels_13217_raw'),
    ('13', '223', '13223', 'Paulding', 'RPD24_V2_13223', 'parcels_13223_raw'),
    ('13', '247', '13247', 'Rockdale', 'RPD24_V2_13247', 'parcels_13247_raw')
ON CONFLICT (county_fips) DO NOTHING;

\echo 'arc_county_map_2024 populated (17 counties, excluding Butts/Haralson/Jasper/Coweta).'

-- -------------------------------------------------------------------------
-- 2. Verify all expected raw parcel tables exist before inserting.
--    This will raise an error and stop if any raw table is missing.
-- -------------------------------------------------------------------------

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT county_fips, county_name, raw_table_name
        FROM acs_5yr_2024.arc_county_map_2024
        WHERE county_fips <> '067'   -- Cobb already loaded; skip its check
        ORDER BY county_fips
    LOOP
        IF to_regclass(format('acs_5yr_2024.%I', r.raw_table_name)) IS NULL THEN
            RAISE EXCEPTION
                'Missing raw parcel table: acs_5yr_2024.% (% county %). '
                'Load it with ogr2ogr before running this script.',
                r.raw_table_name, r.county_name, r.county_fips;
        END IF;
        RAISE NOTICE 'OK: acs_5yr_2024.% found for % (%)',
            r.raw_table_name, r.county_name, r.county_fips;
    END LOOP;
END $$;

\echo 'All raw parcel tables verified.'

-- -------------------------------------------------------------------------
-- 3. Insert parcel records for the 16 remaining counties.
--    Skips Cobb (067) since it is already present.
--    Uses ON CONFLICT DO NOTHING so the script is safe to re-run.
-- -------------------------------------------------------------------------

DO $$
DECLARE
    r      record;
    n_ins  bigint;
BEGIN
    FOR r IN
        SELECT *
        FROM acs_5yr_2024.arc_county_map_2024
        WHERE county_fips <> '067'   -- skip Cobb
        ORDER BY county_fips
    LOOP
        RAISE NOTICE 'Inserting parcels for % (%) from % ...',
            r.county_name, r.county_fips, r.raw_table_name;

        EXECUTE format($sql$
            INSERT INTO acs_5yr_2024.arc_parcels_2024 (
                county_fips,
                arcid_mr,
                apn,
                state_fips,
                county_name,
                full_fips,
                source_layer,
                area_buildi,
                year_built,
                parcel_acreage_mr,
                latitude,
                longitude,
                lu_tranche_mr,
                lu_type_mr,
                pecas_resi_tranche_mr,
                property_use_standardized,
                geom
            )
            SELECT
                %L::text                                          AS county_fips,
                "ARCID_MR"::text                                  AS arcid_mr,
                apn::text                                         AS apn,
                %L::text                                          AS state_fips,
                %L::text                                          AS county_name,
                %L::text                                          AS full_fips,
                %L::text                                          AS source_layer,
                "AreaBuildi"::integer                             AS area_buildi,
                "YearBuilt"::integer                              AS year_built,
                "ParcelAcreage_MR"::double precision              AS parcel_acreage_mr,
                latitude::double precision                        AS latitude,
                longitude::double precision                       AS longitude,
                "LUTranche_MR"::text                              AS lu_tranche_mr,
                "LUType_MR"::text                                 AS lu_type_mr,
                "PECASResiTranche_MR"::text                       AS pecas_resi_tranche_mr,
                "PropertyUseStandardized"::integer                AS property_use_standardized,
                ST_Multi(ST_Force2D(geom))::geometry(MultiPolygon, 4326) AS geom
            FROM acs_5yr_2024.%I
            ON CONFLICT (county_fips, arcid_mr) DO NOTHING
        $sql$,
            r.county_fips,
            r.state_fips,
            r.county_name,
            r.full_fips,
            r.source_layer,
            r.raw_table_name
        );

        GET DIAGNOSTICS n_ins = ROW_COUNT;
        RAISE NOTICE 'Inserted % rows for % (%)', n_ins, r.county_name, r.county_fips;
    END LOOP;
END $$;

\echo 'All remaining county parcels inserted.'

-- -------------------------------------------------------------------------
-- 4. Refresh indexes and statistics
-- -------------------------------------------------------------------------

ANALYZE acs_5yr_2024.arc_parcels_2024;

\echo 'ANALYZE complete.'

-- -------------------------------------------------------------------------
-- 5. Summary row counts by county
-- -------------------------------------------------------------------------

SELECT
    county_fips,
    county_name,
    COUNT(*) AS parcel_count
FROM acs_5yr_2024.arc_parcels_2024
GROUP BY county_fips, county_name
ORDER BY county_fips;

\echo 'Done. arc_parcels_2024 now contains all 18 available ARC counties.'
