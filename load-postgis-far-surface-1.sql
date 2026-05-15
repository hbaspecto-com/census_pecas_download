-- =============================================================================
-- load-postgis-far-surface-1.sql
--
-- Creates a kernel-smoothed FAR (Floor Area Ratio) surface as a PostGIS layer
-- suitable for loading into QGIS.
--
-- Implements the design described in docs/Kernel_Map_Of_FAR.md:
--   - All parcels (not just residential) contribute to the surface
--   - Effective land area is capped to prevent large parks/farms from
--     dominating the denominator
--   - A Gaussian distance-decay kernel smooths FAR over a 1200m search radius
--     with a 400m kernel scale (dense urban / suburban setting)
--   - Results are stored on a 100m regular grid
--   - log1p(local_far) is included for logarithmic visualization in QGIS
--
-- Prerequisites:
--   - acs_5yr_2024.arc_parcels_2024 is fully populated (all counties)
--   - PostGIS extension is available
--
-- Usage:
--   psql -h leduc.office.hbaspecto.com -d atlanta_db -U postgres \
--        -f load-postgis-far-surface-1.sql
--
-- Output layer for QGIS:
--   acs_5yr_2024.far_surface_100m
--   Key columns: grid_id, geom, local_far, log1p_local_far,
--                weighted_building_sqft, weighted_effective_land_sqft,
--                nearby_parcel_count
-- =============================================================================

\set ON_ERROR_STOP on

-- =============================================================================
-- Step 1: Build parcel points with effective land area
-- =============================================================================

\echo 'Step 1: Creating far_parcel_points...'

DROP MATERIALIZED VIEW IF EXISTS acs_5yr_2024.far_parcel_points CASCADE;

CREATE MATERIALIZED VIEW acs_5yr_2024.far_parcel_points AS
SELECT
    county_fips || '_' || arcid_mr                    AS parcel_id,
    ST_Transform(ST_PointOnSurface(geom)::geometry(Point, 4326), 2240)    AS pt,

    -- Building square footage (area_buildi is already in sqft)
    COALESCE(area_buildi, 0)::double precision         AS building_sqft,

    -- Land square footage: parcel_acreage_mr * 43560 sq ft per acre
    (COALESCE(parcel_acreage_mr, 0) * 43560.0)::double precision AS land_sqft_from_acreage,
    ST_Area(ST_Transform(geom, 2240)) AS land_sqft_from_geom,

    -- Effective land area: cap large parks, farms, and giant parcels
    -- to prevent them from diluting the FAR surface excessively.
    -- Uses lu_tranche_mr to identify regional/open land classes.
    CASE
        WHEN lu_tranche_mr ILIKE '%PARK%'
          OR lu_tranche_mr ILIKE '%FOREST%'
          OR lu_tranche_mr ILIKE '%FARM%'
          OR lu_tranche_mr ILIKE '%AGRICULTURE%'
          OR lu_tranche_mr ILIKE '%WATER%'
          OR lu_tranche_mr ILIKE '%WETLAND%'
            THEN LEAST(ST_Area(ST_Transform(geom, 2240)), 200000.0)

        WHEN ST_Area(ST_Transform(geom, 2240)) > 500000.0
            THEN 200000.0

        ELSE (ST_Area(ST_Transform(geom, 2240)))
    END::double precision                              AS effective_land_sqft,

    lu_tranche_mr,
    pecas_resi_tranche_mr,
    geom
FROM acs_5yr_2024.arc_parcels_2024
WHERE geom IS NOT NULL
  AND NOT ST_IsEmpty(geom);
--  AND parcel_acreage_mr IS NOT NULL
--  AND parcel_acreage_mr > 0;

CREATE INDEX far_parcel_points_pt_gix
ON acs_5yr_2024.far_parcel_points
USING GIST (pt);

ANALYZE acs_5yr_2024.far_parcel_points;

\echo 'Step 1 complete.'

SELECT
    COUNT(*)                                    AS total_parcels,
    SUM(building_sqft)                          AS total_building_sqft,
    SUM(land_sqft_from_geom)                    AS total_land_sqft_from_geom,
    SUM(land_sqft_from_acreage)                 AS total_land_sqft_from_acreage,
    SUM(effective_land_sqft)                    AS total_effective_land_sqft,
    SUM(CASE WHEN building_sqft > 0 THEN 1 ELSE 0 END) AS parcels_with_building_sqft
FROM acs_5yr_2024.far_parcel_points;

-- =============================================================================
-- Step 2: Generate 100m regular grid covering all parcel points
-- =============================================================================

\echo 'Step 2: Creating far_grid_400ft...'

DROP MATERIALIZED VIEW IF EXISTS acs_5yr_2024.far_grid_400ft CASCADE;

-- Grid generated via generate_series for compatibility with all PostGIS versions.
-- We use EPSG:2240.
CREATE MATERIALIZED VIEW acs_5yr_2024.far_grid_400ft AS
WITH bounds AS (
    -- Compute the bounding box of all parcel points, projected to UTM 16N
    SELECT
        ST_XMin(env) AS xmin,
        ST_YMin(env) AS ymin,
        ST_XMax(env) AS xmax,
        ST_YMax(env) AS ymax
    FROM (
        SELECT ST_Envelope(
                   ST_Transform(
                       ST_Collect(geom),
                       2240
                   )
               ) AS env
        FROM acs_5yr_2024.v_acs_sqft_regression_diagnostics_arc_2024
    ) e
),
grid_cells AS (
    SELECT
        row_number() OVER ()                                        AS grid_id,
        -- 400 ft cell
        ST_SetSRID(
            ST_MakeEnvelope(
                b.xmin + x * 400.0,
                b.ymin + y * 400.0,
                b.xmin + (x + 1) * 400.0,
                b.ymin + (y + 1) * 400.0
            ),
            2240
        )                                                           AS geom

    FROM bounds b,
         generate_series(0, CEIL((b.xmax - b.xmin) / 400.0)::int - 1) AS x,
         generate_series(0, CEIL((b.ymax - b.ymin) / 400.0)::int - 1) AS y
)
-- Keep only cells that have at least one parcel point within 5000ft
-- (avoids materializing millions of empty cells outside the study area)
SELECT gc.grid_id, gc.geom
FROM grid_cells gc
WHERE EXISTS (
    SELECT 1
    FROM acs_5yr_2024.far_parcel_points p
    WHERE ST_DWithin(
              gc.geom,
              p.pt,
              5000
          )
    LIMIT 1
);

CREATE INDEX far_grid_400ft_geom_gix
ON acs_5yr_2024.far_grid_400ft
USING GIST (geom);

ANALYZE acs_5yr_2024.far_grid_400ft;

\echo 'Step 2 complete.'

SELECT COUNT(*) AS grid_cell_count FROM acs_5yr_2024.far_grid_400ft;


