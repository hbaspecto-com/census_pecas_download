\set ON_ERROR_STOP on

\echo Loading ACS residential sqft regression diagnostics...

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS acs_5yr_2024;

-- -------------------------------------------------------------------------
-- 1. Base diagnostics table
-- -------------------------------------------------------------------------
DROP TABLE IF EXISTS acs_5yr_2024.acs_sqft_regression_diagnostics_arc_2024 CASCADE;

CREATE TABLE acs_5yr_2024.acs_sqft_regression_diagnostics_arc_2024 (
  geoid                         text PRIMARY KEY,
  log_res_sqft_per_hh           double precision,
  occupied_households_bg        double precision,
  predicted_log_sqft_per_hh     double precision,
  residual                      double precision,
  predicted_sqft_per_hh         double precision,
  model_name                    text,
  abs_residual                  double precision,
  abs_pct_error                 double precision
);

\copy acs_5yr_2024.acs_sqft_regression_diagnostics_arc_2024 (geoid, log_res_sqft_per_hh, occupied_households_bg, predicted_log_sqft_per_hh, residual, predicted_sqft_per_hh, model_name, abs_residual, abs_pct_error) FROM '/nfs/home/sja/repos/census_pecas_download/outputs/acs_sqft_regression_diagnostics_arc_2024.csv' WITH (FORMAT csv, HEADER true);

ANALYZE acs_5yr_2024.acs_sqft_regression_diagnostics_arc_2024;

\echo Loaded diagnostics table.

-- -------------------------------------------------------------------------
-- 2. QGIS-ready geometry view
-- -------------------------------------------------------------------------
DROP VIEW IF EXISTS acs_5yr_2024.v_acs_sqft_regression_diagnostics_arc_2024;

CREATE VIEW acs_5yr_2024.v_acs_sqft_regression_diagnostics_arc_2024 AS
SELECT
  row_number() OVER () AS gid,
  g.geom::geometry(MultiPolygon, 4326) AS geom,
  g.state,
  g.county,
  g.tract,
  g.block_group,
  d.geoid,
  d.log_res_sqft_per_hh,
  exp(d.log_res_sqft_per_hh) AS observed_sqft_per_hh,
  d.occupied_households_bg,
  d.predicted_log_sqft_per_hh,
  d.predicted_sqft_per_hh,
  d.predicted_sqft_per_hh * d.occupied_households_bg AS predicted_total_res_sqft,
  d.residual,
  d.abs_residual,
  d.abs_pct_error,
  d.model_name
FROM acs_5yr_2024.arc_bg_geom_2024 g
JOIN acs_5yr_2024.acs_sqft_regression_diagnostics_arc_2024 d
  ON d.geoid = g.geoid;

\echo Created QGIS view: acs_5yr_2024.v_acs_sqft_regression_diagnostics_arc_2024
\echo Done.