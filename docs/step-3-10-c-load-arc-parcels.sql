DROP TABLE IF EXISTS acs_5yr_2024.arc_parcels_2024 CASCADE;

CREATE TABLE acs_5yr_2024.arc_parcels_2024 (
    county_fips text NOT NULL,
    arcid_mr text NOT NULL,
    apn text,
    state_fips text,
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
    geom geometry(MultiPolygon, 4326),
    CONSTRAINT arc_parcels_2024_pk PRIMARY KEY (county_fips, arcid_mr)
);

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
                %L::text AS county_fips,
                "ARCID_MR"::text AS arcid_mr,
                apn::text AS apn,
                %L::text AS state_fips,
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
            r.county_fips,
            r.state_fips,
            r.county_name,
            r.full_fips,
            r.source_layer,
            r.raw_table_name
        );
    END LOOP;
END $$;

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