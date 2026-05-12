-- =============================================================================
-- load-postgis-steps12-17-all-counties.sql
--
-- Runs Steps 12–17 from step-3-load-postgis-2024.md for all 17 available
-- ARC counties (Cobb + the 16 loaded by load-parcels-remaining-counties.sql).
-- Coweta County (13077) is excluded due to a geometry/CRS issue that caused
-- only ~43.6% spatial assignment rate, similar to the 3 counties with no
-- parcel layer (Butts/035, Haralson/143, Jasper/159).
--
-- Prerequisites:
--   - acs_5yr_2024.arc_parcels_2024 is fully populated (all 17 counties, excl. Coweta).
--   - acs_5yr_2024.arc_bg_geom_2024 exists (2024 TIGER block group geometry).
--   - acs_5yr_2024.arc_county_map_2024 exists and is populated.
--
-- Steps performed:
--   12. Create arc_built_res_parcels_2024 (built-residential filter)
--   13. Create arc_parcel_bg_assignment_2024 (spatial assignment by parcel geom)
--   14. QA parcel-to-block-group assignment
--   15. Create arc_parcel_bg_assignment_latlon_2024 (lat/lon fallback assignment)
--   16. Create arc_bg_res_sqft_2024 (block group residential sqft aggregation)
--   17. Export CSV outputs
--
-- Usage:
--   psql -h leduc.office.hbaspecto.com -d atlanta_db -U postgres \
--        -f load-postgis-steps12-17-all-counties.sql
-- =============================================================================

\set ON_ERROR_STOP on

-- =============================================================================
-- Step 12: Create Built-Residential ARC Parcel Table
-- =============================================================================

\echo 'Step 12: Creating arc_built_res_parcels_2024...'

DROP TABLE IF EXISTS acs_5yr_2024.arc_built_res_parcels_2024 CASCADE;

CREATE TABLE acs_5yr_2024.arc_built_res_parcels_2024 AS
SELECT
    *,
    area_buildi AS res_sqft
FROM acs_5yr_2024.arc_parcels_2024
WHERE pecas_resi_tranche_mr IN (
    'SFR LESS THAN 1 ACRE',
    'SFR 1 ACRE OR MORE',
    'CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX',
    'MFR LESS THAN 3 FLOORS',
    'MFR 3 FLOORS OR MORE'
);

ALTER TABLE acs_5yr_2024.arc_built_res_parcels_2024
ADD CONSTRAINT arc_built_res_parcels_2024_pk PRIMARY KEY (county_fips, arcid_mr);

CREATE INDEX arc_built_res_parcels_2024_gix
ON acs_5yr_2024.arc_built_res_parcels_2024
USING GIST (geom);

CREATE INDEX arc_built_res_parcels_2024_county_idx
ON acs_5yr_2024.arc_built_res_parcels_2024 (county_fips);

CREATE INDEX arc_built_res_parcels_2024_resi_idx
ON acs_5yr_2024.arc_built_res_parcels_2024 (pecas_resi_tranche_mr);

ANALYZE acs_5yr_2024.arc_built_res_parcels_2024;

\echo 'Step 12 complete. QA summary:'

SELECT
    COUNT(*) AS built_res_records,
    SUM(res_sqft) AS total_res_sqft,
    SUM(CASE WHEN res_sqft = 0 THEN 1 ELSE 0 END) AS zero_res_sqft_records,
    SUM(CASE WHEN geom IS NULL OR ST_IsEmpty(geom) THEN 1 ELSE 0 END) AS null_or_empty_geom_count,
    SUM(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 ELSE 0 END) AS missing_latlon_count
FROM acs_5yr_2024.arc_built_res_parcels_2024;

SELECT
    county_fips,
    county_name,
    COUNT(*) AS built_res_records,
    SUM(res_sqft) AS total_res_sqft,
    SUM(CASE WHEN res_sqft = 0 THEN 1 ELSE 0 END) AS zero_res_sqft_records
FROM acs_5yr_2024.arc_built_res_parcels_2024
GROUP BY county_fips, county_name
ORDER BY county_fips;

-- =============================================================================
-- Step 13: Assign Built-Residential Parcels to Block Groups by Parcel Geometry
-- =============================================================================

\echo 'Step 13: Creating arc_parcel_bg_assignment_2024 (spatial assignment)...'

DROP TABLE IF EXISTS acs_5yr_2024.arc_parcel_bg_assignment_2024 CASCADE;

CREATE TABLE acs_5yr_2024.arc_parcel_bg_assignment_2024 AS
SELECT
    p.arcid_mr,
    p.apn,
    p.state_fips,
    p.county_fips,
    p.county_name,
    p.full_fips,
    p.source_layer,
    p.res_sqft,
    p.area_buildi,
    p.year_built,
    p.parcel_acreage_mr,
    p.pecas_resi_tranche_mr,
    p.lu_tranche_mr,
    p.lu_type_mr,
    p.property_use_standardized,
    p.latitude,
    p.longitude,
    bg.geoid,
    bg.county AS bg_county_fips,
    ST_PointOnSurface(p.geom)::geometry(Point, 4326) AS assignment_point,
    p.geom AS parcel_geom
FROM acs_5yr_2024.arc_built_res_parcels_2024 p
LEFT JOIN LATERAL (
    SELECT
        b.geoid,
        b.county
    FROM acs_5yr_2024.arc_bg_geom_2024 b
    WHERE p.county_fips = b.county
      AND ST_Covers(b.geom, ST_PointOnSurface(p.geom))
    ORDER BY b.geoid
    LIMIT 1
) bg ON true;

ALTER TABLE acs_5yr_2024.arc_parcel_bg_assignment_2024
ADD CONSTRAINT arc_parcel_bg_assignment_2024_pk PRIMARY KEY (county_fips, arcid_mr);

CREATE INDEX arc_parcel_bg_assignment_2024_geoid_idx
ON acs_5yr_2024.arc_parcel_bg_assignment_2024 (geoid);

CREATE INDEX arc_parcel_bg_assignment_2024_county_idx
ON acs_5yr_2024.arc_parcel_bg_assignment_2024 (county_fips);

CREATE INDEX arc_parcel_bg_assignment_2024_point_gix
ON acs_5yr_2024.arc_parcel_bg_assignment_2024
USING GIST (assignment_point);

CREATE INDEX arc_parcel_bg_assignment_2024_geom_gix
ON acs_5yr_2024.arc_parcel_bg_assignment_2024
USING GIST (parcel_geom);

ANALYZE acs_5yr_2024.arc_parcel_bg_assignment_2024;

\echo 'Step 13 complete.'

-- =============================================================================
-- Step 14: QA Parcel-to-Block-Group Assignment
-- =============================================================================

\echo 'Step 14: QA parcel-to-block-group assignment...'

-- Overall assignment QA
SELECT
    COUNT(*) AS built_res_records,
    COUNT(geoid) AS assigned_records,
    COUNT(*) - COUNT(geoid) AS unmatched_records,
    SUM(res_sqft) AS total_res_sqft,
    SUM(CASE WHEN geoid IS NOT NULL THEN res_sqft ELSE 0 END) AS assigned_res_sqft,
    SUM(CASE WHEN geoid IS NULL THEN res_sqft ELSE 0 END) AS unmatched_res_sqft
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024;

-- County-level assignment QA
SELECT
    county_fips,
    county_name,
    COUNT(*) AS built_res_records,
    COUNT(geoid) AS assigned_records,
    COUNT(*) - COUNT(geoid) AS unmatched_records,
    ROUND(100.0 * COUNT(geoid) / NULLIF(COUNT(*), 0), 4) AS assigned_pct,
    SUM(res_sqft) AS total_res_sqft,
    SUM(CASE WHEN geoid IS NOT NULL THEN res_sqft ELSE 0 END) AS assigned_res_sqft,
    SUM(CASE WHEN geoid IS NULL THEN res_sqft ELSE 0 END) AS unmatched_res_sqft
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
GROUP BY county_fips, county_name
ORDER BY county_fips;

-- Confirm assigned GEOID county matches parcel county
SELECT
    COUNT(*) AS assigned_records,
    SUM(CASE WHEN county_fips = substring(geoid from 3 for 3) THEN 1 ELSE 0 END) AS matching_county_records,
    SUM(CASE WHEN county_fips <> substring(geoid from 3 for 3) THEN 1 ELSE 0 END) AS mismatching_county_records
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
WHERE geoid IS NOT NULL;

-- Check for duplicate assignments (should return zero rows)
SELECT
    arcid_mr,
    county_fips,
    COUNT(*) AS n
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
GROUP BY arcid_mr, county_fips
HAVING COUNT(*) > 1
ORDER BY n DESC, arcid_mr;

-- Block groups with built-residential parcels by county
SELECT
    substring(geoid from 3 for 3) AS county_fips,
    COUNT(DISTINCT geoid) AS block_groups_with_built_res_parcels
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
WHERE geoid IS NOT NULL
GROUP BY substring(geoid from 3 for 3)
ORDER BY county_fips;

-- Compare to all ARC block groups
SELECT
    bg.county AS county_fips,
    COUNT(DISTINCT bg.geoid) AS total_block_groups,
    COUNT(DISTINCT a.geoid) AS block_groups_with_built_res_parcels,
    COUNT(DISTINCT bg.geoid) - COUNT(DISTINCT a.geoid) AS block_groups_without_built_res_parcels
FROM acs_5yr_2024.arc_bg_geom_2024 bg
LEFT JOIN acs_5yr_2024.arc_parcel_bg_assignment_2024 a
  ON bg.geoid = a.geoid
GROUP BY bg.county
ORDER BY bg.county;

\echo 'Step 14 complete.'

-- =============================================================================
-- Step 15: Optional QA/Fallback Assignment Using Latitude/Longitude
-- =============================================================================

\echo 'Step 15: Creating arc_parcel_bg_assignment_latlon_2024 (lat/lon fallback)...'

DROP TABLE IF EXISTS acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 CASCADE;

CREATE TABLE acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 AS
SELECT
    p.arcid_mr,
    p.county_fips,
    bg.geoid AS latlon_geoid,
    ST_SetSRID(ST_MakePoint(p.longitude, p.latitude), 4326)::geometry(Point, 4326) AS latlon_point
FROM acs_5yr_2024.arc_built_res_parcels_2024 p
LEFT JOIN LATERAL (
    SELECT
        b.geoid
    FROM acs_5yr_2024.arc_bg_geom_2024 b
    WHERE p.county_fips = b.county
      AND p.longitude IS NOT NULL
      AND p.latitude IS NOT NULL
      AND ST_Covers(
          b.geom,
          ST_SetSRID(ST_MakePoint(p.longitude, p.latitude), 4326)
      )
    ORDER BY b.geoid
    LIMIT 1
) bg ON true;

ALTER TABLE acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024
ADD CONSTRAINT arc_parcel_bg_assignment_latlon_2024_pk PRIMARY KEY (county_fips, arcid_mr);

CREATE INDEX arc_parcel_bg_assignment_latlon_2024_geoid_idx
ON acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 (latlon_geoid);

CREATE INDEX arc_parcel_bg_assignment_latlon_2024_county_idx
ON acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 (county_fips);

CREATE INDEX arc_parcel_bg_assignment_latlon_2024_point_gix
ON acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024
USING GIST (latlon_point);

ANALYZE acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024;

-- Compare parcel-geometry assignment with lat/lon assignment
SELECT
    COUNT(*) AS records,
    SUM(CASE WHEN g.geoid = l.latlon_geoid THEN 1 ELSE 0 END) AS same_assignment,
    SUM(CASE WHEN g.geoid IS DISTINCT FROM l.latlon_geoid THEN 1 ELSE 0 END) AS different_assignment,
    SUM(CASE WHEN g.geoid IS NULL THEN 1 ELSE 0 END) AS geometry_unmatched,
    SUM(CASE WHEN l.latlon_geoid IS NULL THEN 1 ELSE 0 END) AS latlon_unmatched
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024 g
JOIN acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 l
  ON g.arcid_mr = l.arcid_mr AND g.county_fips = l.county_fips;

-- County-level comparison
SELECT
    g.county_fips,
    COUNT(*) AS records,
    SUM(CASE WHEN g.geoid = l.latlon_geoid THEN 1 ELSE 0 END) AS same_assignment,
    SUM(CASE WHEN g.geoid IS DISTINCT FROM l.latlon_geoid THEN 1 ELSE 0 END) AS different_assignment,
    SUM(CASE WHEN g.geoid IS NULL THEN 1 ELSE 0 END) AS geometry_unmatched,
    SUM(CASE WHEN l.latlon_geoid IS NULL THEN 1 ELSE 0 END) AS latlon_unmatched
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024 g
JOIN acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 l
  ON g.arcid_mr = l.arcid_mr AND g.county_fips = l.county_fips
GROUP BY g.county_fips
ORDER BY g.county_fips;

\echo 'Step 15 complete.'

-- =============================================================================
-- Step 16: Create Step 4-Ready Block Group Residential Square Footage Table
-- =============================================================================

\echo 'Step 16: Creating arc_bg_res_sqft_2024...'

DROP TABLE IF EXISTS acs_5yr_2024.arc_bg_res_sqft_2024 CASCADE;

CREATE TABLE acs_5yr_2024.arc_bg_res_sqft_2024 AS
SELECT
    bg.geoid,
    bg.state,
    bg.county,
    m.county_name,
    bg.tract,
    bg.block_group,
    COUNT(a.arcid_mr) AS residential_record_count,
    COALESCE(SUM(a.res_sqft), 0)::bigint AS total_res_sqft,
    COALESCE(SUM(CASE WHEN a.res_sqft = 0 THEN 1 ELSE 0 END), 0)::integer AS zero_res_sqft_record_count,
    bg.geom
FROM acs_5yr_2024.arc_bg_geom_2024 bg
LEFT JOIN acs_5yr_2024.arc_county_map_2024 m
  ON bg.county = m.county_fips
LEFT JOIN acs_5yr_2024.arc_parcel_bg_assignment_2024 a
  ON bg.geoid = a.geoid
GROUP BY
    bg.geoid,
    bg.state,
    bg.county,
    m.county_name,
    bg.tract,
    bg.block_group,
    bg.geom;

ALTER TABLE acs_5yr_2024.arc_bg_res_sqft_2024
ADD CONSTRAINT arc_bg_res_sqft_2024_pk PRIMARY KEY (geoid);

CREATE INDEX arc_bg_res_sqft_2024_county_idx
ON acs_5yr_2024.arc_bg_res_sqft_2024 (county);

CREATE INDEX arc_bg_res_sqft_2024_gix
ON acs_5yr_2024.arc_bg_res_sqft_2024
USING GIST (geom);

ANALYZE acs_5yr_2024.arc_bg_res_sqft_2024;

\echo 'Step 16 complete. QA summary:'

SELECT
    COUNT(*) AS block_groups,
    SUM(residential_record_count) AS residential_record_count,
    SUM(total_res_sqft) AS total_res_sqft,
    SUM(CASE WHEN residential_record_count = 0 THEN 1 ELSE 0 END) AS block_groups_with_no_built_res_records,
    SUM(CASE WHEN total_res_sqft = 0 THEN 1 ELSE 0 END) AS block_groups_with_zero_res_sqft
FROM acs_5yr_2024.arc_bg_res_sqft_2024;

SELECT
    county,
    county_name,
    COUNT(*) AS block_groups,
    SUM(residential_record_count) AS residential_record_count,
    SUM(total_res_sqft) AS total_res_sqft,
    SUM(CASE WHEN residential_record_count = 0 THEN 1 ELSE 0 END) AS block_groups_with_no_built_res_records,
    SUM(CASE WHEN total_res_sqft = 0 THEN 1 ELSE 0 END) AS block_groups_with_zero_res_sqft
FROM acs_5yr_2024.arc_bg_res_sqft_2024
GROUP BY county, county_name
ORDER BY county;

-- =============================================================================
-- Step 17: Export Step 3 and Step 4 Outputs to CSV
-- =============================================================================

\echo 'Step 17: Exporting CSV outputs...'

-- Parcel-to-block-group assignment export
\copy ( SELECT arcid_mr, apn, state_fips, county_fips, county_name, full_fips, source_layer, res_sqft, area_buildi, year_built, parcel_acreage_mr, pecas_resi_tranche_mr, lu_tranche_mr, lu_type_mr, property_use_standardized, latitude, longitude, geoid FROM acs_5yr_2024.arc_parcel_bg_assignment_2024 ORDER BY county_fips, geoid, arcid_mr ) TO '/nfs/home/sja/repos/census_pecas_download/outputs/arc_parcel_bg_assignment_2024.csv' WITH (FORMAT csv, HEADER true)

\echo 'Exported arc_parcel_bg_assignment_2024.csv'

-- Block group residential square footage export
\copy ( SELECT geoid, state, county, county_name, tract, block_group, residential_record_count, total_res_sqft, zero_res_sqft_record_count FROM acs_5yr_2024.arc_bg_res_sqft_2024 ORDER BY geoid ) TO '/nfs/home/sja/repos/census_pecas_download/outputs/arc_bg_res_sqft_2024.csv' WITH (FORMAT csv, HEADER true)

\echo 'Exported arc_bg_res_sqft_2024.csv'

-- Unmatched parcel export
\copy ( SELECT arcid_mr, apn, state_fips, county_fips, county_name, full_fips, source_layer, res_sqft, pecas_resi_tranche_mr, lu_tranche_mr, lu_type_mr, latitude, longitude, ST_AsText(assignment_point) AS assignment_point_wkt FROM acs_5yr_2024.arc_parcel_bg_assignment_2024 WHERE geoid IS NULL ORDER BY county_fips, res_sqft DESC, arcid_mr ) TO '/nfs/home/sja/repos/census_pecas_download/outputs/arc_unmatched_built_res_parcels_2024.csv' WITH (FORMAT csv, HEADER true)

\echo 'Exported arc_unmatched_built_res_parcels_2024.csv'

-- Geometry-vs-latlon mismatch export
\copy ( SELECT g.arcid_mr, g.apn, g.county_fips, g.county_name, g.source_layer, g.res_sqft, g.pecas_resi_tranche_mr, g.geoid AS geometry_geoid, l.latlon_geoid, g.latitude, g.longitude FROM acs_5yr_2024.arc_parcel_bg_assignment_2024 g JOIN acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 l ON g.arcid_mr = l.arcid_mr AND g.county_fips = l.county_fips WHERE g.geoid IS DISTINCT FROM l.latlon_geoid ORDER BY g.county_fips, g.res_sqft DESC, g.arcid_mr ) TO '/nfs/home/sja/repos/census_pecas_download/outputs/arc_geometry_vs_latlon_bg_mismatch_2024.csv' WITH (FORMAT csv, HEADER true)

\echo 'Exported arc_geometry_vs_latlon_bg_mismatch_2024.csv'

-- =============================================================================
-- Step 18: Final QA Summary
-- =============================================================================

\echo 'Step 18: Final QA summary...'

SELECT
    'arc_bg_geom_2024' AS table_name,
    COUNT(*) AS records
FROM acs_5yr_2024.arc_bg_geom_2024

UNION ALL

SELECT
    'arc_parcels_2024' AS table_name,
    COUNT(*) AS records
FROM acs_5yr_2024.arc_parcels_2024

UNION ALL

SELECT
    'arc_built_res_parcels_2024' AS table_name,
    COUNT(*) AS records
FROM acs_5yr_2024.arc_built_res_parcels_2024

UNION ALL

SELECT
    'arc_parcel_bg_assignment_2024' AS table_name,
    COUNT(*) AS records
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024

UNION ALL

SELECT
    'arc_bg_res_sqft_2024' AS table_name,
    COUNT(*) AS records
FROM acs_5yr_2024.arc_bg_res_sqft_2024;

-- Assignment success by county
SELECT
    county_fips,
    county_name,
    COUNT(*) AS built_res_records,
    COUNT(geoid) AS assigned_records,
    COUNT(*) - COUNT(geoid) AS unmatched_records,
    ROUND(100.0 * COUNT(geoid) / NULLIF(COUNT(*), 0), 4) AS assigned_pct,
    SUM(res_sqft) AS total_res_sqft,
    SUM(CASE WHEN geoid IS NULL THEN res_sqft ELSE 0 END) AS unmatched_res_sqft
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
GROUP BY county_fips, county_name
ORDER BY county_fips;

-- Block group coverage by county
SELECT
    bg.county AS county_fips,
    m.county_name,
    COUNT(DISTINCT bg.geoid) AS total_block_groups,
    COUNT(DISTINCT CASE WHEN sq.residential_record_count > 0 THEN sq.geoid END) AS block_groups_with_built_res_records,
    COUNT(DISTINCT bg.geoid)
      - COUNT(DISTINCT CASE WHEN sq.residential_record_count > 0 THEN sq.geoid END) AS block_groups_without_built_res_records,
    COALESCE(SUM(sq.residential_record_count), 0) AS residential_record_count,
    COALESCE(SUM(sq.total_res_sqft), 0) AS total_res_sqft
FROM acs_5yr_2024.arc_bg_geom_2024 bg
LEFT JOIN acs_5yr_2024.arc_county_map_2024 m
  ON bg.county = m.county_fips
LEFT JOIN acs_5yr_2024.arc_bg_res_sqft_2024 sq
  ON bg.geoid = sq.geoid
GROUP BY bg.county, m.county_name
ORDER BY bg.county;

\echo 'Done. All steps 12-17 complete for all 17 available ARC counties (Coweta excluded).'
\echo 'CSV outputs written to outputs/ directory.'
