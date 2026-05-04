# 2024 ARC Parcel-to-Block-Group PostGIS Load Instructions

This document loads 2024 block group geometry and 2024 ARC parcel data into PostGIS, then assigns built-residential parcels to 2024 ACS/TIGER block groups for all available ARC counties.

## Scope

- Database: `atlanta_db`
- Host: `leduc.office.hbaspecto.com`
- Schema: `acs_5yr_2024`
- Geography: 21 ARC counties in Georgia, subject to parcel-layer availability in the FileGDB
- Block group vintage: 2024 TIGER/ACS block groups
- Parcel source: `inputs/RegionalParcelDataSet2024/RPD24_V2.gdb`
- Assignment method: parcel polygon `ST_PointOnSurface()` assigned to block group polygon using `ST_Covers()`
- QA/fallback method: provided parcel `longitude`, `latitude`

## ARC County FIPS List

| County FIPS | Full FIPS | County |
|---|---|---|
| `013` | `13013` | Barrow |
| `015` | `13015` | Bartow |
| `035` | `13035` | Butts |
| `045` | `13045` | Carroll |
| `057` | `13057` | Cherokee |
| `063` | `13063` | Clayton |
| `067` | `13067` | Cobb |
| `077` | `13077` | Coweta |
| `085` | `13085` | Dawson |
| `089` | `13089` | DeKalb |
| `097` | `13097` | Douglas |
| `113` | `13113` | Fayette |
| `117` | `13117` | Forsyth |
| `121` | `13121` | Fulton |
| `135` | `13135` | Gwinnett |
| `143` | `13143` | Haralson |
| `151` | `13151` | Henry |
| `159` | `13159` | Jasper |
| `217` | `13217` | Newton |
| `223` | `13223` | Paulding |
| `247` | `13247` | Rockdale |

## Important Notes Before Running

- The 2024 TIGER block group shapefile is NAD83 / EPSG:4269. This workflow transforms block group geometry to EPSG:4326 in the working PostGIS table.
- The parcel inventory indicates parcel geometry is WGS84 / EPSG:4326.
- The parcel FileGDB may not contain every ARC county as a separate layer. This workflow explicitly checks layer availability before loading.
- The parcel load uses `-lco LAUNDER=NO` so mixed-case field names such as `"ARCID_MR"` and `"AreaBuildi"` remain available to SQL.
- The parcel load uses `-dim XY` because the source geometry is 3D measured multipolygon, but this workflow only needs 2D geometry.
- Spatial assignment uses `LEFT JOIN LATERAL ... LIMIT 1` to guarantee at most one assigned block group per parcel, even if a point falls exactly on a boundary.

## Prerequisites

These instructions assume:

1. GDAL/OGR command-line tools are available.
2. PostgreSQL/PostGIS is available.
3. Environment variables are stored in `leduc.env`.
4. The parcel FileGDB exists at the path given by `$GDB_PATH`.
5. The 2024 Georgia block group TIGER zip will be downloaded to `$DOWNLOAD_DIR/tl_2024_13_bg.zip`.

## Environment Setup

Run these shell commands first.

```bash
source leduc.env

cd "$PROJECT_ROOT"

mkdir -p "$DOWNLOAD_DIR" "$OUTPUT_DIR"
```

Optional sanity check:

```bash
echo "$PGHOST"
echo "$PGDATABASE"
echo "$PGUSER"
echo "$PGPORT"
echo "$PROJECT_ROOT"
echo "$GDB_PATH"
echo "$DOWNLOAD_DIR"
echo "$OUTPUT_DIR"
```

## Step 1: Download 2024 Georgia Block Group Boundaries

```bash
wget -O "$DOWNLOAD_DIR/tl_2024_13_bg.zip" \
  https://www2.census.gov/geo/tiger/TIGER2024/BG/tl_2024_13_bg.zip
```

Optional quick check:

```bash
ogrinfo /vsizip/"$DOWNLOAD_DIR"/tl_2024_13_bg.zip/tl_2024_13_bg.shp -so tl_2024_13_bg
```

Expected highlights:

```text
Geometry: Polygon
GEOID: String (12.0)
STATEFP: String (2.0)
COUNTYFP: String (3.0)
TRACTCE: String (6.0)
BLKGRPCE: String (1.0)
Layer SRS: NAD83 / EPSG:4269
```

## Step 2: Create 2024 Schema and Enable PostGIS

Run this in `psql`.

```sql
\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS acs_5yr_2024;
```

## Step 3: Load 2024 Georgia Block Groups into PostGIS

Run this from the shell, not inside `psql`.

```bash
ogr2ogr \
  -f PostgreSQL \
  "PG:host=${PGHOST} port=${PGPORT} dbname=${PGDATABASE} user=${PGUSER}" \
  /vsizip/"${DOWNLOAD_DIR}"/tl_2024_13_bg.zip/tl_2024_13_bg.shp \
  -nln acs_5yr_2024.ga_bg_geom_2024_raw \
  -nlt MULTIPOLYGON \
  -lco GEOMETRY_NAME=geom \
  -lco FID=gid \
  -overwrite
```

## Step 4: Create ARC-Only 2024 Block Group Geometry Table

Run this in `psql`.

```sql
DROP TABLE IF EXISTS acs_5yr_2024.arc_bg_geom_2024 CASCADE;

CREATE TABLE acs_5yr_2024.arc_bg_geom_2024 AS
SELECT
    geoid::text AS geoid,
    statefp::text AS state,
    countyfp::text AS county,
    tractce::text AS tract,
    blkgrpce::text AS block_group,
    namelsad::text AS namelsad,
    ST_Multi(ST_Transform(ST_Force2D(geom), 4326))::geometry(MultiPolygon, 4326) AS geom
FROM acs_5yr_2024.ga_bg_geom_2024_raw
WHERE statefp = '13'
  AND countyfp IN (
      '013', '015', '035', '045', '057', '063', '067',
      '077', '085', '089', '097', '113', '117', '121',
      '135', '143', '151', '159', '217', '223', '247'
  );

ALTER TABLE acs_5yr_2024.arc_bg_geom_2024
ADD CONSTRAINT arc_bg_geom_2024_pk PRIMARY KEY (geoid);

CREATE INDEX arc_bg_geom_2024_gix
ON acs_5yr_2024.arc_bg_geom_2024
USING GIST (geom);

CREATE INDEX arc_bg_geom_2024_county_idx
ON acs_5yr_2024.arc_bg_geom_2024 (county);

ANALYZE acs_5yr_2024.arc_bg_geom_2024;
```

## Step 5: QA 2024 ARC Block Group Geometry

Run this in `psql`.

```sql
SELECT
    COUNT(*) AS arc_block_groups,
    COUNT(DISTINCT geoid) AS distinct_geoids,
    COUNT(*) - COUNT(DISTINCT geoid) AS duplicate_geoid_count,
    SUM(CASE WHEN length(geoid) = 12 THEN 1 ELSE 0 END) AS good_geoid_length_count,
    SUM(CASE WHEN ST_IsEmpty(geom) OR geom IS NULL THEN 1 ELSE 0 END) AS empty_or_null_geom_count,
    ST_SRID(geom) AS srid
FROM acs_5yr_2024.arc_bg_geom_2024
GROUP BY ST_SRID(geom);
```

Expected:

- `duplicate_geoid_count = 0`
- `empty_or_null_geom_count = 0`
- `srid = 4326`

County summary:

```sql
SELECT
    county,
    COUNT(*) AS block_group_count
FROM acs_5yr_2024.arc_bg_geom_2024
GROUP BY county
ORDER BY county;
```

Confirm only ARC counties are present:

```sql
SELECT DISTINCT county
FROM acs_5yr_2024.arc_bg_geom_2024
ORDER BY county;
```

## Step 6: Check Parcel Layer Availability in the FileGDB

Run this from the shell.

```bash
echo "Checking ARC parcel layer availability in: $GDB_PATH"

ogrinfo "$GDB_PATH" | grep -E "RPD24_V2_(13013|13015|13035|13045|13057|13063|13067|13077|13085|13089|13097|13113|13117|13121|13135|13143|13151|13159|13217|13223|13247)"
```

The target ARC county layer list is:

```text
RPD24_V2_13013
RPD24_V2_13015
RPD24_V2_13035
RPD24_V2_13045
RPD24_V2_13057
RPD24_V2_13063
RPD24_V2_13067
RPD24_V2_13077
RPD24_V2_13085
RPD24_V2_13089
RPD24_V2_13097
RPD24_V2_13113
RPD24_V2_13117
RPD24_V2_13121
RPD24_V2_13135
RPD24_V2_13143
RPD24_V2_13151
RPD24_V2_13159
RPD24_V2_13217
RPD24_V2_13223
RPD24_V2_13247
```

If any expected layer is missing, decide whether to:

1. stop and investigate, or
2. temporarily remove that county from the shell load list and document it as unavailable.


### MISSING COUNTIES
035 Butts
143 Haralson
159 Jasper

## Step 7: Load Available ARC Parcel Layers from the 2024 File Geodatabase

This section loads each county layer to a raw PostGIS table.

### Considering the 3 missing counties run from shell:

```bash
PGCONN="PG:host=${PGHOST} port=${PGPORT} dbname=${PGDATABASE} user=${PGUSER}"

for COUNTY in \
  13013 \
  13015 \
  13045 \
  13057 \
  13063 \
  13067 \
  13077 \
  13085 \
  13089 \
  13097 \
  13113 \
  13117 \
  13121 \
  13135 \
  13151 \
  13217 \
  13223 \
  13247
do
  echo "Loading parcel layer RPD24_V2_${COUNTY}..."

  ogr2ogr \
    -f PostgreSQL \
    "${PGCONN}" \
    "${GDB_PATH}" \
    "RPD24_V2_${COUNTY}" \
    -nln "acs_5yr_2024.parcels_${COUNTY}_raw" \
    -nlt MULTIPOLYGON \
    -dim XY \
    -lco GEOMETRY_NAME=geom \
    -lco FID=gid \
    -lco LAUNDER=NO \
    -overwrite

  if [ $? -ne 0 ]; then
    echo "ERROR: Failed to load RPD24_V2_${COUNTY}. Stop and investigate before continuing."
    exit 1
  fi
done
```

### This one has all 21 counties:

```bash
PGCONN="PG:host=${PGHOST} port=${PGPORT} dbname=${PGDATABASE} user=${PGUSER}"

for COUNTY in \
  13013 \
  13015 \
  13035 \
  13045 \
  13057 \
  13063 \
  13067 \
  13077 \
  13085 \
  13089 \
  13097 \
  13113 \
  13117 \
  13121 \
  13135 \
  13143 \
  13151 \
  13159 \
  13217 \
  13223 \
  13247
do
  echo "Loading parcel layer RPD24_V2_${COUNTY}..."

  ogr2ogr \
    -f PostgreSQL \
    "${PGCONN}" \
    "${GDB_PATH}" \
    "RPD24_V2_${COUNTY}" \
    -nln "acs_5yr_2024.parcels_${COUNTY}_raw" \
    -nlt MULTIPOLYGON \
    -dim XY \
    -lco GEOMETRY_NAME=geom \
    -lco FID=gid \
    -lco LAUNDER=NO \
    -overwrite

  if [ $? -ne 0 ]; then
    echo "ERROR: Failed to load RPD24_V2_${COUNTY}. Stop and investigate before continuing."
    exit 1
  fi
done
```

## Step 8: QA One Raw Parcel Layer Before Continuing

Run this in `psql` after loading at least Cobb (`13067`).

```sql
SELECT
    ST_SRID(geom) AS srid,
    COUNT(*) AS records
FROM acs_5yr_2024.parcels_13067_raw
GROUP BY ST_SRID(geom)
ORDER BY srid;
```

Expected:

```text
srid = 4326
```

Also inspect columns:

```sql
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'acs_5yr_2024'
  AND table_name = 'parcels_13067_raw'
ORDER BY ordinal_position;
```

Expected important columns include:

```text
ARCID_MR
apn
AreaBuildi
YearBuilt
ParcelAcreage_MR
latitude
longitude
LUTranche_MR
LUType_MR
PECASResiTranche_MR
PropertyUseStandardized
geom
```

If the raw parcel SRID is `0`, use the `ST_SetSRID` geometry expression in Step 10.

If the raw parcel SRID is something other than `0` or `4326`, use the `ST_Transform` geometry expression in Step 10.

## Step 9: Create County Mapping Table

Run this in `psql`.

```sql
DROP TABLE IF EXISTS acs_5yr_2024.arc_county_map_2024 CASCADE;

CREATE TABLE acs_5yr_2024.arc_county_map_2024 (
    state_fips text NOT NULL,
    county_fips text PRIMARY KEY,
    full_fips text NOT NULL,
    county_name text NOT NULL,
    source_layer text NOT NULL,
    raw_table_name text NOT NULL
);

INSERT INTO acs_5yr_2024.arc_county_map_2024 (
    state_fips,
    county_fips,
    full_fips,
    county_name,
    source_layer,
    raw_table_name
)
VALUES
    ('13', '013', '13013', 'Barrow',   'RPD24_V2_13013', 'parcels_13013_raw'),
    ('13', '015', '13015', 'Bartow',   'RPD24_V2_13015', 'parcels_13015_raw'),
    ('13', '035', '13035', 'Butts',    'RPD24_V2_13035', 'parcels_13035_raw'),
    ('13', '045', '13045', 'Carroll',  'RPD24_V2_13045', 'parcels_13045_raw'),
    ('13', '057', '13057', 'Cherokee', 'RPD24_V2_13057', 'parcels_13057_raw'),
    ('13', '063', '13063', 'Clayton',  'RPD24_V2_13063', 'parcels_13063_raw'),
    ('13', '067', '13067', 'Cobb',     'RPD24_V2_13067', 'parcels_13067_raw'),
    ('13', '077', '13077', 'Coweta',   'RPD24_V2_13077', 'parcels_13077_raw'),
    ('13', '085', '13085', 'Dawson',   'RPD24_V2_13085', 'parcels_13085_raw'),
    ('13', '089', '13089', 'DeKalb',   'RPD24_V2_13089', 'parcels_13089_raw'),
    ('13', '097', '13097', 'Douglas',  'RPD24_V2_13097', 'parcels_13097_raw'),
    ('13', '113', '13113', 'Fayette',  'RPD24_V2_13113', 'parcels_13113_raw'),
    ('13', '117', '13117', 'Forsyth',  'RPD24_V2_13117', 'parcels_13117_raw'),
    ('13', '121', '13121', 'Fulton',   'RPD24_V2_13121', 'parcels_13121_raw'),
    ('13', '135', '13135', 'Gwinnett', 'RPD24_V2_13135', 'parcels_13135_raw'),
    ('13', '143', '13143', 'Haralson', 'RPD24_V2_13143', 'parcels_13143_raw'),
    ('13', '151', '13151', 'Henry',    'RPD24_V2_13151', 'parcels_13151_raw'),
    ('13', '159', '13159', 'Jasper',   'RPD24_V2_13159', 'parcels_13159_raw'),
    ('13', '217', '13217', 'Newton',   'RPD24_V2_13217', 'parcels_13217_raw'),
    ('13', '223', '13223', 'Paulding', 'RPD24_V2_13223', 'parcels_13223_raw'),
    ('13', '247', '13247', 'Rockdale', 'RPD24_V2_13247', 'parcels_13247_raw');
```

Check whether all expected raw tables exist:

```sql
SELECT
    m.county_fips,
    m.county_name,
    m.source_layer,
    m.raw_table_name,
    CASE
        WHEN c.table_name IS NULL THEN 'MISSING'
        ELSE 'FOUND'
    END AS raw_table_status
FROM acs_5yr_2024.arc_county_map_2024 m
LEFT JOIN information_schema.tables c
  ON c.table_schema = 'acs_5yr_2024'
 AND c.table_name = m.raw_table_name
ORDER BY m.county_fips;
```

If any raw table is `MISSING`, stop and decide whether to remove that county from `arc_county_map_2024` for this run.

## Step 10: Create Unified ARC Parcel Table

Run this in `psql`.

```sql
DROP TABLE IF EXISTS acs_5yr_2024.arc_parcels_2024 CASCADE;

CREATE TABLE acs_5yr_2024.arc_parcels_2024 (
    arcid_mr text PRIMARY KEY,
    apn text,
    state_fips text,
    county_fips text,
    county_name text,
    full_fips text,
    source_layer text,
    area_buildi integer,
    year_built integer,
    parcel_acreage_mr double precision,
    latitude double precision,
    longitude double precision,
    lu_tranche_mr text,
    lu_type_mr text,
    pecas_resi_tranche_mr text,
    property_use_standardized integer,
    geom geometry(MultiPolygon, 4326)
);
```

### Step 10 implementation notes

The raw county parcel layers were first loaded into PostGIS tables named:

```text
acs_5yr_2024.parcels_13067_raw
```

and equivalent `parcels_XXXXX_raw` tables for other loaded counties.

The raw PostGIS parcel tables use `geom` as the geometry column. Do **not** use `Shape` in SQL after the `ogr2ogr` load; `Shape` is the source FileGDB geometry name, while `geom` is the PostGIS geometry column created by the load command.

For a small test load, Cobb was inserted first with `LIMIT 5`, then reloaded without `LIMIT`. This is recommended when debugging because it confirms:

- raw table column names are correct,
- `geom` is the correct geometry column,
- geometry casts to `geometry(MultiPolygon, 4326)`,
- and the target table accepts the records.

### Step 10A: Optional Cobb test insert

Use this optional test insert before loading a full county or all counties.

```sql
TRUNCATE TABLE acs_5yr_2024.arc_parcels_2024;

INSERT INTO acs_5yr_2024.arc_parcels_2024 (
    arcid_mr,
    apn,
    state_fips,
    county_fips,
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
    "ARCID_MR"::text,
    apn::text,
    '13',
    '067',
    'Cobb',
    '13067',
    'RPD24_V2_13067',
    "AreaBuildi"::integer,
    "YearBuilt"::integer,
    "ParcelAcreage_MR"::double precision,
    latitude::double precision,
    longitude::double precision,
    "LUTranche_MR"::text,
    "LUType_MR"::text,
    "PECASResiTranche_MR"::text,
    "PropertyUseStandardized"::integer,
    ST_Multi(ST_Force2D(geom))::geometry(MultiPolygon, 4326)
FROM acs_5yr_2024.parcels_13067_raw
LIMIT 5;
```

Confirm the test insert worked:

```sql
SELECT COUNT(*) AS n
FROM acs_5yr_2024.arc_parcels_2024;
```

Expected:

```text
n = 5
```

If this fails with a missing geometry column, confirm the raw table columns:

```sql
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'acs_5yr_2024'
  AND table_name = 'parcels_13067_raw'
ORDER BY ordinal_position;
```

Expected important columns include:

```text
ARCID_MR
apn
AreaBuildi
YearBuilt
ParcelAcreage_MR
latitude
longitude
LUTranche_MR
LUType_MR
PECASResiTranche_MR
PropertyUseStandardized
geom
```

### Step 10B: Cobb full insert

After the test insert succeeds, run the full Cobb insert.

```sql
TRUNCATE TABLE acs_5yr_2024.arc_parcels_2024;

INSERT INTO acs_5yr_2024.arc_parcels_2024 (
    arcid_mr,
    apn,
    state_fips,
    county_fips,
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
    "ARCID_MR"::text,
    apn::text,
    '13',
    '067',
    'Cobb',
    '13067',
    'RPD24_V2_13067',
    "AreaBuildi"::integer,
    "YearBuilt"::integer,
    "ParcelAcreage_MR"::double precision,
    latitude::double precision,
    longitude::double precision,
    "LUTranche_MR"::text,
    "LUType_MR"::text,
    "PECASResiTranche_MR"::text,
    "PropertyUseStandardized"::integer,
    ST_Multi(ST_Force2D(geom))::geometry(MultiPolygon, 4326)
FROM acs_5yr_2024.parcels_13067_raw;
```

Confirm the full Cobb insert:

```sql
SELECT COUNT(*) AS n
FROM acs_5yr_2024.arc_parcels_2024;
```

Expected Cobb result:

```text
n = 264126
```

### Step 10C: Full county insert option

After the single-county insert pattern is verified, either repeat the same `INSERT ... SELECT` pattern county-by-county or use a controlled dynamic SQL block based on `acs_5yr_2024.arc_county_map_2024`.

Use this dynamic block only after confirming all desired rows in `arc_county_map_2024` point to raw tables that exist.

Check raw table availability first:

```sql
SELECT
    m.county_fips,
    m.county_name,
    m.raw_table_name,
    CASE
        WHEN c.table_name IS NULL THEN 'MISSING'
        ELSE 'FOUND'
    END AS raw_table_status
FROM acs_5yr_2024.arc_county_map_2024 m
LEFT JOIN information_schema.tables c
  ON c.table_schema = 'acs_5yr_2024'
 AND c.table_name = m.raw_table_name
ORDER BY m.county_fips;
```

If any raw table is `MISSING`, remove that county from `arc_county_map_2024` for this run or stop and investigate.

```sql
TRUNCATE TABLE acs_5yr_2024.arc_parcels_2024;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT *
        FROM acs_5yr_2024.arc_county_map_2024
        ORDER BY county_fips
    LOOP
        IF to_regclass(format('acs_5yr_2024.%I', r.raw_table_name)) IS NULL THEN
            RAISE EXCEPTION 'Missing raw parcel table: acs_5yr_2024.%', r.raw_table_name;
        END IF;

        RAISE NOTICE 'Inserting parcel records for % (%) from %',
            r.county_name, r.county_fips, r.raw_table_name;

        EXECUTE format($sql$
            INSERT INTO acs_5yr_2024.arc_parcels_2024 (
                arcid_mr,
                apn,
                state_fips,
                county_fips,
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
                "ARCID_MR"::text AS arcid_mr,
                apn::text AS apn,
                %L::text AS state_fips,
                %L::text AS county_fips,
                %L::text AS county_name,
                %L::text AS full_fips,
                %L::text AS source_layer,
                "AreaBuildi"::integer AS area_buildi,
                "YearBuilt"::integer AS year_built,
                "ParcelAcreage_MR"::double precision AS parcel_acreage_mr,
                latitude::double precision AS latitude,
                longitude::double precision AS longitude,
                "LUTranche_MR"::text AS lu_tranche_mr,
                "LUType_MR"::text AS lu_type_mr,
                "PECASResiTranche_MR"::text AS pecas_resi_tranche_mr,
                "PropertyUseStandardized"::integer AS property_use_standardized,
                ST_Multi(ST_Force2D(geom))::geometry(MultiPolygon, 4326) AS geom
            FROM acs_5yr_2024.%I
        $sql$,
            r.state_fips,
            r.county_fips,
            r.county_name,
            r.full_fips,
            r.source_layer,
            r.raw_table_name
        );
    END LOOP;
END $$;
```

If raw parcel SRID is `0`, use this geometry expression instead:

```sql
ST_Multi(ST_SetSRID(ST_Force2D(geom), 4326))::geometry(MultiPolygon, 4326) AS geom
```

If raw parcel SRID is another valid SRID, use this geometry expression instead:

```sql
ST_Multi(ST_Transform(ST_Force2D(geom), 4326))::geometry(MultiPolygon, 4326) AS geom
```

Create indexes and analyze after loading the unified table.

```sql
CREATE INDEX arc_parcels_2024_gix
ON acs_5yr_2024.arc_parcels_2024
USING GIST (geom);

CREATE INDEX arc_parcels_2024_county_idx
ON acs_5yr_2024.arc_parcels_2024 (county_fips);

CREATE INDEX arc_parcels_2024_resi_idx
ON acs_5yr_2024.arc_parcels_2024 (pecas_resi_tranche_mr);

CREATE INDEX arc_parcels_2024_latlon_idx
ON acs_5yr_2024.arc_parcels_2024 (longitude, latitude);

ANALYZE acs_5yr_2024.arc_parcels_2024;
```

## Step 11: QA Unified ARC Parcel Table

Run this in `psql`.

```sql
SELECT
    COUNT(*) AS parcel_records,
    COUNT(DISTINCT arcid_mr) AS distinct_arcid_mr,
    COUNT(*) - COUNT(DISTINCT arcid_mr) AS duplicate_arcid_mr_count,
    SUM(CASE WHEN geom IS NULL OR ST_IsEmpty(geom) THEN 1 ELSE 0 END) AS null_or_empty_geom_count,
    SUM(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 ELSE 0 END) AS missing_latlon_count,
    ST_SRID(geom) AS srid
FROM acs_5yr_2024.arc_parcels_2024
GROUP BY ST_SRID(geom);
```

Expected Cobb result:

```text
parcel_records = 264126
distinct_arcid_mr = 264126
duplicate_arcid_mr_count = 0
null_or_empty_geom_count = 0
missing_latlon_count = 0
srid = 4326
```

County-level parcel counts:

```sql
SELECT
    county_fips,
    county_name,
    source_layer,
    COUNT(*) AS parcel_records
FROM acs_5yr_2024.arc_parcels_2024
GROUP BY county_fips, county_name, source_layer
ORDER BY county_fips;
```

Check loaded counties against county map:

```sql
SELECT
    m.county_fips,
    m.county_name,
    COUNT(p.arcid_mr) AS parcel_records
FROM acs_5yr_2024.arc_county_map_2024 m
LEFT JOIN acs_5yr_2024.arc_parcels_2024 p
  ON m.county_fips = p.county_fips
GROUP BY m.county_fips, m.county_name
ORDER BY m.county_fips;
```

Residential category counts:

```sql
SELECT
    pecas_resi_tranche_mr,
    COUNT(*) AS parcel_records,
    SUM(area_buildi) AS total_area_buildi,
    SUM(CASE WHEN area_buildi = 0 THEN 1 ELSE 0 END) AS zero_area_buildi_records
FROM acs_5yr_2024.arc_parcels_2024
GROUP BY pecas_resi_tranche_mr
ORDER BY parcel_records DESC;
```

County-level residential category counts:

```sql
SELECT
    county_fips,
    county_name,
    pecas_resi_tranche_mr,
    COUNT(*) AS parcel_records,
    SUM(area_buildi) AS total_area_buildi
FROM acs_5yr_2024.arc_parcels_2024
GROUP BY county_fips, county_name, pecas_resi_tranche_mr
ORDER BY county_fips, parcel_records DESC;
```

## Step 12: Create Built-Residential ARC Parcel Table

This uses the first-pass built-residential categories identified in the parcel inventory.

Run this in `psql`.

```sql
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
```

Add constraints and indexes.

```sql
ALTER TABLE acs_5yr_2024.arc_built_res_parcels_2024
ADD CONSTRAINT arc_built_res_parcels_2024_pk PRIMARY KEY (arcid_mr);

CREATE INDEX arc_built_res_parcels_2024_gix
ON acs_5yr_2024.arc_built_res_parcels_2024
USING GIST (geom);

CREATE INDEX arc_built_res_parcels_2024_county_idx
ON acs_5yr_2024.arc_built_res_parcels_2024 (county_fips);

CREATE INDEX arc_built_res_parcels_2024_resi_idx
ON acs_5yr_2024.arc_built_res_parcels_2024 (pecas_resi_tranche_mr);

ANALYZE acs_5yr_2024.arc_built_res_parcels_2024;
```

QA:

```sql
SELECT
    COUNT(*) AS built_res_records,
    SUM(res_sqft) AS total_res_sqft,
    SUM(CASE WHEN res_sqft = 0 THEN 1 ELSE 0 END) AS zero_res_sqft_records,
    SUM(CASE WHEN geom IS NULL OR ST_IsEmpty(geom) THEN 1 ELSE 0 END) AS null_or_empty_geom_count,
    SUM(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 ELSE 0 END) AS missing_latlon_count
FROM acs_5yr_2024.arc_built_res_parcels_2024;
```

Expected Cobb result:

```text
built_res_records = 236007
total_res_sqft = 593866703
zero_res_sqft_records = 493
null_or_empty_geom_count = 0
missing_latlon_count = 0
```

County-level built-residential summary:

```sql
SELECT
    county_fips,
    county_name,
    COUNT(*) AS built_res_records,
    SUM(res_sqft) AS total_res_sqft,
    SUM(CASE WHEN res_sqft = 0 THEN 1 ELSE 0 END) AS zero_res_sqft_records
FROM acs_5yr_2024.arc_built_res_parcels_2024
GROUP BY county_fips, county_name
ORDER BY county_fips;
```

## Step 13: Assign Built-Residential Parcels to Block Groups by Parcel Geometry

This is the primary Step 3 assignment table.

It assigns by `ST_PointOnSurface(parcel_geom)`, using `LEFT JOIN LATERAL ... LIMIT 1` to guarantee one output row per parcel.

Run this in `psql`.

```sql
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
```

Add constraints and indexes.

```sql
ALTER TABLE acs_5yr_2024.arc_parcel_bg_assignment_2024
ADD CONSTRAINT arc_parcel_bg_assignment_2024_pk PRIMARY KEY (arcid_mr);

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
```

## Step 14: QA Parcel-to-Block-Group Assignment

Overall assignment QA:

```sql
SELECT
    COUNT(*) AS built_res_records,
    COUNT(geoid) AS assigned_records,
    COUNT(*) - COUNT(geoid) AS unmatched_records,
    SUM(res_sqft) AS total_res_sqft,
    SUM(CASE WHEN geoid IS NOT NULL THEN res_sqft ELSE 0 END) AS assigned_res_sqft,
    SUM(CASE WHEN geoid IS NULL THEN res_sqft ELSE 0 END) AS unmatched_res_sqft
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024;
```

County-level assignment QA:

```sql
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
```

Confirm assigned GEOID county matches parcel county:

```sql
SELECT
    COUNT(*) AS assigned_records,
    SUM(CASE WHEN county_fips = substring(geoid from 3 for 3) THEN 1 ELSE 0 END) AS matching_county_records,
    SUM(CASE WHEN county_fips <> substring(geoid from 3 for 3) THEN 1 ELSE 0 END) AS mismatching_county_records
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
WHERE geoid IS NOT NULL;
```

List unmatched parcels:

```sql
SELECT
    arcid_mr,
    apn,
    county_fips,
    county_name,
    source_layer,
    res_sqft,
    pecas_resi_tranche_mr,
    latitude,
    longitude,
    ST_AsText(assignment_point) AS assignment_point_wkt
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
WHERE geoid IS NULL
ORDER BY res_sqft DESC
LIMIT 200;
```

Check duplicate assignments. This should return zero rows:

```sql
SELECT
    arcid_mr,
    COUNT(*) AS n
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
GROUP BY arcid_mr
HAVING COUNT(*) > 1
ORDER BY n DESC, arcid_mr;
```

Block groups with built-residential parcels by county:

```sql
SELECT
    substring(geoid from 3 for 3) AS county_fips,
    COUNT(DISTINCT geoid) AS block_groups_with_built_res_parcels
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
WHERE geoid IS NOT NULL
GROUP BY substring(geoid from 3 for 3)
ORDER BY county_fips;
```

Compare to all ARC block groups:

```sql
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
```

## Step 15: Optional QA/Fallback Assignment Using Latitude/Longitude

Create a second assignment table using provided parcel coordinates.

This also uses `LEFT JOIN LATERAL ... LIMIT 1` to guarantee one output row per parcel.

Run this in `psql`.

```sql
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
```

Add constraints and indexes.

```sql
ALTER TABLE acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024
ADD CONSTRAINT arc_parcel_bg_assignment_latlon_2024_pk PRIMARY KEY (arcid_mr);

CREATE INDEX arc_parcel_bg_assignment_latlon_2024_geoid_idx
ON acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 (latlon_geoid);

CREATE INDEX arc_parcel_bg_assignment_latlon_2024_county_idx
ON acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 (county_fips);

CREATE INDEX arc_parcel_bg_assignment_latlon_2024_point_gix
ON acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024
USING GIST (latlon_point);

ANALYZE acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024;
```

Compare parcel-geometry assignment with latitude/longitude assignment.

```sql
SELECT
    COUNT(*) AS records,
    SUM(CASE WHEN g.geoid = l.latlon_geoid THEN 1 ELSE 0 END) AS same_assignment,
    SUM(CASE WHEN g.geoid IS DISTINCT FROM l.latlon_geoid THEN 1 ELSE 0 END) AS different_assignment,
    SUM(CASE WHEN g.geoid IS NULL THEN 1 ELSE 0 END) AS geometry_unmatched,
    SUM(CASE WHEN l.latlon_geoid IS NULL THEN 1 ELSE 0 END) AS latlon_unmatched
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024 g
JOIN acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 l
  ON g.arcid_mr = l.arcid_mr;
```

County-level comparison:

```sql
SELECT
    g.county_fips,
    COUNT(*) AS records,
    SUM(CASE WHEN g.geoid = l.latlon_geoid THEN 1 ELSE 0 END) AS same_assignment,
    SUM(CASE WHEN g.geoid IS DISTINCT FROM l.latlon_geoid THEN 1 ELSE 0 END) AS different_assignment,
    SUM(CASE WHEN g.geoid IS NULL THEN 1 ELSE 0 END) AS geometry_unmatched,
    SUM(CASE WHEN l.latlon_geoid IS NULL THEN 1 ELSE 0 END) AS latlon_unmatched
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024 g
JOIN acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 l
  ON g.arcid_mr = l.arcid_mr
GROUP BY g.county_fips
ORDER BY g.county_fips;
```

Inspect differences:

```sql
SELECT
    g.arcid_mr,
    g.apn,
    g.county_fips,
    g.county_name,
    g.res_sqft,
    g.pecas_resi_tranche_mr,
    g.geoid AS geometry_geoid,
    l.latlon_geoid,
    g.latitude,
    g.longitude
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024 g
JOIN acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 l
  ON g.arcid_mr = l.arcid_mr
WHERE g.geoid IS DISTINCT FROM l.latlon_geoid
ORDER BY g.res_sqft DESC
LIMIT 200;
```

## Step 16: Create Step 4-Ready Block Group Residential Square Footage Table

This is technically Step 4, but it is useful to create immediately after Step 3.

Run this in `psql`.

```sql
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
```

Add constraints and indexes.

```sql
ALTER TABLE acs_5yr_2024.arc_bg_res_sqft_2024
ADD CONSTRAINT arc_bg_res_sqft_2024_pk PRIMARY KEY (geoid);

CREATE INDEX arc_bg_res_sqft_2024_county_idx
ON acs_5yr_2024.arc_bg_res_sqft_2024 (county);

CREATE INDEX arc_bg_res_sqft_2024_gix
ON acs_5yr_2024.arc_bg_res_sqft_2024
USING GIST (geom);

ANALYZE acs_5yr_2024.arc_bg_res_sqft_2024;
```

QA block group aggregation:

```sql
SELECT
    COUNT(*) AS block_groups,
    SUM(residential_record_count) AS residential_record_count,
    SUM(total_res_sqft) AS total_res_sqft,
    SUM(CASE WHEN residential_record_count = 0 THEN 1 ELSE 0 END) AS block_groups_with_no_built_res_records,
    SUM(CASE WHEN total_res_sqft = 0 THEN 1 ELSE 0 END) AS block_groups_with_zero_res_sqft
FROM acs_5yr_2024.arc_bg_res_sqft_2024;
```

County-level block group aggregation:

```sql
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
```

Largest block groups by residential square footage:

```sql
SELECT
    geoid,
    county,
    county_name,
    residential_record_count,
    total_res_sqft
FROM acs_5yr_2024.arc_bg_res_sqft_2024
ORDER BY total_res_sqft DESC
LIMIT 50;
```

## Step 17: Export Step 3 and Step 4 Outputs to CSV

Run these in `psql`.

Parcel-to-block-group assignment export:

```sql
\copy (
    SELECT
        arcid_mr,
        apn,
        state_fips,
        county_fips,
        county_name,
        full_fips,
        source_layer,
        res_sqft,
        area_buildi,
        year_built,
        parcel_acreage_mr,
        pecas_resi_tranche_mr,
        lu_tranche_mr,
        lu_type_mr,
        property_use_standardized,
        latitude,
        longitude,
        geoid
    FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
    ORDER BY county_fips, geoid, arcid_mr
) TO '/nfs/home/sja/repos/census_pecas_download/outputs/arc_parcel_bg_assignment_2024.csv'
WITH (FORMAT csv, HEADER true);
```

Block group residential square footage export:

```sql
\copy (
    SELECT
        geoid,
        state,
        county,
        county_name,
        tract,
        block_group,
        residential_record_count,
        total_res_sqft,
        zero_res_sqft_record_count
    FROM acs_5yr_2024.arc_bg_res_sqft_2024
    ORDER BY geoid
) TO '/nfs/home/sja/repos/census_pecas_download/outputs/arc_bg_res_sqft_2024.csv'
WITH (FORMAT csv, HEADER true);
```

Unmatched parcel export:

```sql
\copy (
    SELECT
        arcid_mr,
        apn,
        state_fips,
        county_fips,
        county_name,
        full_fips,
        source_layer,
        res_sqft,
        pecas_resi_tranche_mr,
        lu_tranche_mr,
        lu_type_mr,
        latitude,
        longitude,
        ST_AsText(assignment_point) AS assignment_point_wkt
    FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
    WHERE geoid IS NULL
    ORDER BY county_fips, res_sqft DESC, arcid_mr
) TO '/nfs/home/sja/repos/census_pecas_download/outputs/arc_unmatched_built_res_parcels_2024.csv'
WITH (FORMAT csv, HEADER true);
```

Geometry-vs-latlon mismatch export:

```sql
\copy (
    SELECT
        g.arcid_mr,
        g.apn,
        g.county_fips,
        g.county_name,
        g.source_layer,
        g.res_sqft,
        g.pecas_resi_tranche_mr,
        g.geoid AS geometry_geoid,
        l.latlon_geoid,
        g.latitude,
        g.longitude
    FROM acs_5yr_2024.arc_parcel_bg_assignment_2024 g
    JOIN acs_5yr_2024.arc_parcel_bg_assignment_latlon_2024 l
      ON g.arcid_mr = l.arcid_mr
    WHERE g.geoid IS DISTINCT FROM l.latlon_geoid
    ORDER BY g.county_fips, g.res_sqft DESC, g.arcid_mr
) TO '/nfs/home/sja/repos/census_pecas_download/outputs/arc_geometry_vs_latlon_bg_mismatch_2024.csv'
WITH (FORMAT csv, HEADER true);
```

## Step 18: Final QA Summary Queries

Run these in `psql` and save or copy the results into the project notes.

Overall final QA:

```sql
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
```

Assignment success by county:

```sql
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
```

Block group coverage by county:

```sql
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
```

Top 100 block groups by total residential square footage:

```sql
SELECT
    geoid,
    county,
    county_name,
    residential_record_count,
    total_res_sqft
FROM acs_5yr_2024.arc_bg_res_sqft_2024
ORDER BY total_res_sqft DESC
LIMIT 100;
```

Top 100 built-residential parcels by square footage:

```sql
SELECT
    arcid_mr,
    apn,
    county_fips,
    county_name,
    geoid,
    res_sqft,
    pecas_resi_tranche_mr,
    lu_tranche_mr,
    lu_type_mr,
    year_built,
    parcel_acreage_mr
FROM acs_5yr_2024.arc_parcel_bg_assignment_2024
ORDER BY res_sqft DESC
LIMIT 100;
```

## Main Deliverables

After running this workflow, the main Step 3 output is:

```text
acs_5yr_2024.arc_parcel_bg_assignment_2024
```

The main Step 4-ready output is:

```text
acs_5yr_2024.arc_bg_res_sqft_2024
```

CSV outputs:

```text
outputs/arc_parcel_bg_assignment_2024.csv
outputs/arc_bg_res_sqft_2024.csv
outputs/arc_unmatched_built_res_parcels_2024.csv
outputs/arc_geometry_vs_latlon_bg_mismatch_2024.csv
```

## Notes

- `ST_PointOnSurface(parcel_geom)` is used instead of `ST_Centroid(parcel_geom)` because it is guaranteed to fall inside the parcel polygon.
- `ST_Covers(block_group_geom, point)` is used instead of only `ST_Contains()` so points exactly on boundaries are more likely to match.
- The assignment join includes `p.county_fips = bg.county` to prevent accidental assignment across county boundaries.
- `LEFT JOIN LATERAL ... LIMIT 1` is used to guarantee no more than one block group assignment per parcel.
- The built-residential filter intentionally excludes:
  - `NOT RESIDENTIAL`
  - `VACANT RESIDENTIAL`
  - `MANUFACTURED RESIDENTIAL`
- `MANUFACTURED RESIDENTIAL` can be revisited later if a separate manufactured-housing square-footage treatment is needed.
- If any county parcel layer is missing from the FileGDB, remove that county from `arc_county_map_2024` for the current run and document the omission in QA notes.
- The raw FileGDB geometry column is named `Shape`, but after `ogr2ogr` loads the raw tables into PostGIS with `-lco GEOMETRY_NAME=geom`, SQL should reference the geometry column as `geom`.