import requests
import pandas as pd
import time
import os
from urllib.parse import quote_plus

arc_counties = [
    "015","013","045","057","063","067","077","089","085","097",
    "113","117","121","135","151","153","223","231","247","255","297"
]

state = "13"

tables = {
    "B25024": "UnitsInStructure",
    "B25003": "Tenure",
    "B25009": "TenureByHHSize",
    "B11016": "HouseholdSize",
    "B19001": "IncomeDist",
    "B03002": "RaceEthnicity"
}

def get_variables(table):
    meta = requests.get(f"https://api.census.gov/data/2023/acs/acs5/groups/{table}.json").json()
    return [v for v in meta["variables"] if v.startswith(table)]

def chunk(lst, n):
    """Split list into chunks of size n."""
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def make_geoid(df):
    # All are strings from API; zero-padding preserved already
    return (df["state"] + df["county"] + df["tract"] + df["block group"])

def fetch_table(table):
    vars_all = get_variables(table)
    rows = []

    for county in arc_counties:
        print(f"  County {county}...")

        # Collect chunks and merge them later
        df_chunks = []

        for var_chunk in chunk(vars_all, 20):
            vars_str = ",".join(var_chunk)

            url = (
                f"https://api.census.gov/data/2023/acs/acs5?"
                f"get=NAME,{vars_str}&"
                f"for=block%20group:*&"
                f"in=state:{state}%20county:{county}"
            )

            # Retry loop
            for attempt in range(5):
                try:
                    resp = requests.get(url, timeout=30)
                    if resp.status_code != 200:
                        print(f"    API error {resp.status_code}: {resp.text[:200]}")
                        time.sleep(2)
                        continue

                    data = resp.json()
                    df = pd.DataFrame(data[1:], columns=data[0])
                    df_chunks.append(df)
                    break  # success, exit retry loop

                except Exception as e:
                    print(f"    Error on attempt {attempt+1}: {e}")
                    time.sleep(2)

        # Merge all chunks horizontally
        df_merged = df_chunks[0]
        for part in df_chunks[1:]:
            df_merged = df_merged.merge(
                part.drop(columns=["NAME"]),
                on=["state","county","tract","block group"],
                how="left"
            )

        rows.append(df_merged)

    out = pd.concat(rows, ignore_index=True)
    out["GEOID"] = make_geoid(out)
    # Optional: reorder GEOID first
    cols = ["GEOID","NAME","state","county","tract","block group"] + [c for c in out.columns if c not in {"GEOID","NAME","state","county","tract","block group"}]
    return out[cols]

def fetch_blockgroup_geometries():
    """
    Download TIGER/Line 2023 block group polygons for specified counties as GeoJSON
    via the TIGERweb MapServer identify endpoint (per-county), then flatten to a table
    with WKT geometry for easy PostGIS copy.
    """
    # TIGERweb layer: Census 2020 Block Groups (Layer 8 in Census2020/tracts_blocks)
    # Endpoint supports where=STATE='13' AND COUNTY='xxx'
    # We'll use the feature server style query endpoint for GeoJSON output.
    base = "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/Tracts_Blocks/MapServer/8/query"

    records = []

    for county in arc_counties:
        params = {
            "where": f"STATE='{state}' AND COUNTY='{county}'",
            "outFields": "STATE,COUNTY,TRACT,BLOCK_GROUP,GEOID",
            "f": "geojson",
            "outSR": "4326",
            "geometryType": "esriGeometryEnvelope",
            "returnGeometry": "true"
        }
        print(f"Downloading geometry for county {county} ...")
        resp = requests.get(base, params=params, timeout=60)
        if resp.status_code != 200:
            print(f"  Geometry API error {resp.status_code}: {resp.text[:200]}")
            continue

        gj = resp.json()
        feats = gj.get("features", [])
        for feat in feats:
            props = feat.get("properties", {})
            geom = feat.get("geometry")
            # Build keys and simple WKT (without external libs)
            # Geometry can be Polygon or MultiPolygon
            wkt = geojson_to_wkt(geom)
            # GEOID: use provided if available; else compose
            geoid = props.get("GEOID") or (props["STATE"] + props["COUNTY"] + props["TRACT"] + str(props["BLOCK_GROUP"]))
            records.append({
                "GEOID": geoid,
                "STATE": props.get("STATE"),
                "COUNTY": props.get("COUNTY"),
                "TRACT": props.get("TRACT"),
                "BLOCK_GROUP": str(props.get("BLOCK_GROUP")),
                "wkt": wkt
            })

    gdf = pd.DataFrame.from_records(records)
    # Normalize naming to match ACS table joins
    gdf.rename(columns={
        "STATE": "state",
        "COUNTY": "county",
        "TRACT": "tract",
        "BLOCK_GROUP": "block group"
    }, inplace=True)
    # Ensure GEOID alignment (strings)
    gdf["GEOID"] = gdf["GEOID"].astype(str)
    return gdf[["GEOID","state","county","tract","block group","wkt"]]

def geojson_to_wkt(geom):
    """
    Convert a minimal GeoJSON geometry to WKT (Polygon/MultiPolygon) without external libs.
    Assumes coordinates are in lon/lat (EPSG:4326).
    """
    if not geom:
        return None
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Polygon":
        rings = []
        for ring in coords:
            rings.append("(" + ", ".join(f"{x} {y}" for x, y in ring) + ")")
        return "POLYGON(" + ", ".join(rings) + ")"
    elif gtype == "MultiPolygon":
        polys = []
        for poly in coords:
            rings = []
            for ring in poly:
                rings.append("(" + ", ".join(f"{x} {y}" for x, y in ring) + ")")
            polys.append("(" + ", ".join(rings) + ")")
        return "MULTIPOLYGON(" + ", ".join(polys) + ")"
    else:
        return None

def to_postgis_instructions(db_url, schema="public"):
    """
    Emit COPY-friendly instructions to load CSVs and geometry into PostGIS and
    create views joining geometry to each ACS table.
    """
    # Filenames/patterns
    geom_csv = "ARC_BG_Geometries_2023.csv"

    print("\nPostGIS load instructions:")
    print("1) In psql, create base tables and enable PostGIS (once):")
    print(f"""\
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS {schema};

-- Geometry base table
DROP TABLE IF EXISTS {schema}.arc_bg_geom_2023 CASCADE;
CREATE TABLE {schema}.arc_bg_geom_2023 (
  geoid text PRIMARY KEY,
  state text,
  county text,
  tract text,
  block_group text,
  wkt text
);
""")

    print("2) COPY geometry CSV into Postgres, then add geometry column:")
    print(f"""\
-- Adjust path as needed
\\copy {schema}.arc_bg_geom_2023 (geoid,state,county,tract,block_group,wkt) FROM '{os.path.abspath(geom_csv)}' WITH (FORMAT csv, HEADER true);

-- Create geometry column from WKT and index
ALTER TABLE {schema}.arc_bg_geom_2023 ADD COLUMN geom geometry(MultiPolygon, 4326);
-- Handle both Polygon and MultiPolygon using ST_Multi
UPDATE {schema}.arc_bg_geom_2023
SET geom = ST_Multi(ST_GeomFromText(wkt, 4326));

CREATE INDEX arc_bg_geom_2023_gix ON {schema}.arc_bg_geom_2023 USING GIST (geom);
""")

    # For each ACS CSV, emit DDL + view
    for table, label in tables.items():
        data_csv = f"ARC_{label}_2023_BG.csv"
        base = f"arc_{label.lower()}_2023_bg"
        print(f"""\
-- {label}
DROP TABLE IF EXISTS {schema}.{base} CASCADE;
CREATE TABLE {schema}.{base} (
  geoid text PRIMARY KEY,
  name text,
  state text,
  county text,
  tract text,
  block_group text
  -- variable columns will be auto-added via COPY if header names match; or we can widen first
);

\\copy {schema}.{base} FROM '{os.path.abspath(data_csv)}' WITH (FORMAT csv, HEADER true);

-- Create a spatial view joining geometry
DROP VIEW IF EXISTS {schema}.v_{base};
CREATE VIEW {schema}.v_{base} AS
SELECT g.geom, d.*
FROM {schema}.arc_bg_geom_2023 g
JOIN {schema}.{base} d ON d.geoid = g.geoid;
""")

    print("Done. You can now query the v_arc_* views as GIS layers.")

def save_csv(df, path):
    df.to_csv(path, index=False)

# Download and save all tables
if __name__ == "__main__":
    os.makedirs(".", exist_ok=True)

    # 1) Data tables
    for table, label in tables.items():
        print(f"Downloading {table} ({label}) ...")
        df = fetch_table(table)
        save_csv(df, f"ARC_{label}_2023_BG.csv")

    # 2) Geometries
    geom_df = fetch_blockgroup_geometries()
    save_csv(geom_df, "ARC_BG_Geometries_2023.csv")

    # 3) Emit PostGIS loading instructions (prints to console)
    # Provide your DB URL to get ready-to-run SQL/COPY steps:
    # Example: db_url = "postgresql://user:pass@localhost:5432/mydb"
    db_url = os.environ.get("POSTGRES_URL", "")
    to_postgis_instructions(db_url or "<postgresql://user:pass@host:port/dbname>", schema="public")

    print("Done.")
