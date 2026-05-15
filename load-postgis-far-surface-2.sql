-- =============================================================================
-- Step 3: Compute kernel-smoothed FAR surface
-- =============================================================================
-- Gaussian kernel:  K(d) = exp( -(d / sigma)^2 )
-- Kernel scale (sigma): 400m  (dense urban / inner suburban)
-- Search radius:        1200m (3 * sigma)
--
-- local_far = SUM( building_sqft_i * K(d_i) )
--           / SUM( effective_land_sqft_i * K(d_i) )
-- =============================================================================

\echo 'Step 3: Creating far_surface_400ft (kernel-smoothed FAR)...'
\echo '        This may take several minutes depending on parcel count.'

DROP MATERIALIZED VIEW IF EXISTS acs_5yr_2024.far_surface_400ft CASCADE;

CREATE MATERIALIZED VIEW acs_5yr_2024.far_surface_400ft AS
SELECT
    g.grid_id,
    g.geom,

    -- Kernel-weighted building sqft (numerator)
    SUM(
        p.building_sqft *
        EXP(-POWER(
            ST_Distance(
                ST_Centroid(g.geom),
                p.pt
            ) / 1600.0,
        2))
    )                                                   AS weighted_building_sqft,

    -- Kernel-weighted effective land sqft (denominator)
    SUM(
        p.effective_land_sqft *
        EXP(-POWER(
            ST_Distance(
                ST_Centroid(g.geom),
                p.pt
            ) / 1600.0,
        2))
    )                                                   AS weighted_effective_land_sqft,

    -- Local FAR: ratio of weighted sums (NOT average of parcel FARs)
    SUM(
        p.building_sqft *
        EXP(-POWER(
            ST_Distance(
                ST_Centroid(g.geom),
                p.pt
            ) / 1600.0,
        2))
    )
    /
    NULLIF(
        SUM(
            p.effective_land_sqft *
            EXP(-POWER(
                ST_Distance(
                    ST_Centroid(g.geom),
                    p.pt
                ) / 1600.0,
            2))
        ),
    0)                                                  AS local_far,

    -- Number of parcels contributing to this cell
    COUNT(p.parcel_id)                                  AS nearby_parcel_count,

    -- Max raw parcel FAR among nearby parcels (anomaly indicator)
    MAX(
        p.building_sqft / NULLIF(p.land_sqft_from_geom, 0)
    )                                                   AS max_nearby_parcel_far,

    -- log1p(local_far) pre-computed for logarithmic visualization in QGIS
    -- (computed inline here since GENERATED ALWAYS AS is not supported on
    --  materialized views)
    ln(1.0 +
        SUM(
            p.building_sqft *
            EXP(-POWER(
                ST_Distance(
                    ST_Centroid(g.geom),
                    p.pt
                ) / 1600.0,
            2))
        )
        /
        NULLIF(
            SUM(
                p.effective_land_sqft *
                EXP(-POWER(
                    ST_Distance(
                        ST_Centroid(g.geom),
                        p.pt
                    ) / 1600.0,
                2))
            ),
        0)
    )                                                   AS log1p_local_far

FROM acs_5yr_2024.far_grid_400ft g
JOIN acs_5yr_2024.far_parcel_points p
  ON ST_DWithin(
         ST_Centroid(g.geom),
         p.pt,
         4800
     )
GROUP BY g.grid_id, g.geom;

-- Spatial index on WGS84 geometry for QGIS rendering
CREATE INDEX far_surface_400ft_geom_gix
ON acs_5yr_2024.far_surface_400ft
USING GIST (geom);

ANALYZE acs_5yr_2024.far_surface_400ft;

\echo 'Step 3 complete.'

-- =============================================================================
-- Step 4: QA summary
-- =============================================================================

\echo 'Step 4: QA summary...'

SELECT
    COUNT(*)                                            AS total_cells,
    COUNT(local_far)                                    AS cells_with_far,
    COUNT(*) - COUNT(local_far)                         AS cells_null_far,
    ROUND(MIN(local_far)::numeric, 4)                   AS min_far,
    ROUND(AVG(local_far)::numeric, 4)                   AS mean_far,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
          (ORDER BY local_far)::numeric, 4)             AS median_far,
    ROUND(MAX(local_far)::numeric, 4)                   AS max_far,
    -- FAR range buckets (from Kernel_Map_Of_FAR.md color scale)
    SUM(CASE WHEN local_far < 0.05                      THEN 1 ELSE 0 END) AS far_rural_open,
    SUM(CASE WHEN local_far >= 0.05  AND local_far < 0.3  THEN 1 ELSE 0 END) AS far_low_density,
    SUM(CASE WHEN local_far >= 0.3   AND local_far < 1.5  THEN 1 ELSE 0 END) AS far_urban_fabric,
    SUM(CASE WHEN local_far >= 1.5   AND local_far < 5.0  THEN 1 ELSE 0 END) AS far_dense_urban,
    SUM(CASE WHEN local_far >= 5.0   AND local_far < 20.0 THEN 1 ELSE 0 END) AS far_suspicious,
    SUM(CASE WHEN local_far >= 20.0                       THEN 1 ELSE 0 END) AS far_severe_error
FROM acs_5yr_2024.far_surface_400ft;

\echo ''
\echo '============================================================'
\echo 'Done. QGIS layer: acs_5yr_2024.far_surface_400ft'
\echo ''
\echo 'Recommended QGIS styling:'
\echo '  - Graduated symbology on column: log1p_local_far'
\echo '  - Or use local_far with manual breaks:'
\echo '    0-0.05   Rural/Open'
\echo '    0.05-0.3 Low Density'
\echo '    0.3-1.5  Urban Fabric'
\echo '    1.5-5    Dense Urban'
\echo '    5-20     Suspicious'
\echo '    20+      Severe Data Error'
\echo '============================================================'