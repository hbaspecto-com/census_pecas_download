import requests
import pandas as pd
import time
import os
import sys
from urllib.parse import quote_plus

arc_counties = [
    "013","015","035","045","057","063","067","077","085","089",
    "097","113","117","121","135","143","151","159","217","223","247"
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

import requests

def fetch_blockgroup_geometries(state="13", arc_counties=None):
    """
    Download TIGER/Line 2020 block group polygons for the specified counties
    using the TIGERweb Census2020 Tracts_Blocks MapServer (Layer 5 = Block Groups).

    Returns: a list of dictionaries:
        { GEOID, STATE, COUNTY, TRACT, BLOCK_GROUP, wkt }
    """

    if arc_counties is None:
        arc_counties = [
            "013","015","035","045","057","063","067","077","085","089",
            "097","113","117","121","135","143","151","159","217","223","247"
        ]

    # ✅ Layer 5 = Block Groups (correct)
    base = (
        "https://tigerweb.geo.census.gov/arcgis/rest/services/"
        "Census2020/Tracts_Blocks/MapServer/5/query"
    )

    records = []
    total_kept = 0

    def digits(s):
        return "".join(ch for ch in s if ch.isdigit())

    for county in arc_counties:
        print(f"Downloading block groups for county {county}...")

        params = {
            "where": f"STATE='{state}' AND COUNTY='{county}'",
            "outFields": "*",
            "returnGeometry": "true",
            "f": "geojson",
            "outSR": "4326",
            "resultRecordCount": 2000,
            "resultOffset": 0,
            "returnExceededLimitFeatures": "true"
        }

        offset = 0
        county_total = 0

        while True:
            params["resultOffset"] = offset

            try:
                resp = requests.get(base, params=params, timeout=60)
            except Exception as ex:
                print(f"  Request error: {ex}")
                break

            if resp.status_code != 200:
                print(f"  HTTP error {resp.status_code}")
                print(resp.text[:300])
                break

            gj = resp.json()
            feats = gj.get("features", [])
            got = len(feats)
            print(f"  Returned {got} features at offset {offset}")

            if got == 0:
                break

            # Preview keys
            if offset == 0 and feats:
                print(f"  Sample keys: {list(feats[0].get('properties',{}).keys())[:10]}")

            for feat in feats:
                props = feat.get("properties") or {}
                geom = feat.get("geometry")

                # Must be polygonal geometry
                if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
                    continue

                wkt = geojson_to_wkt(geom)
                if not wkt:
                    continue

                # Direct fields from Layer 5
                st = digits(props.get("STATE", ""))
                co = digits(props.get("COUNTY", ""))
                tr = digits(props.get("TRACT", ""))
                bg = digits(props.get("BLOCK_GROUP", ""))
                geoid = digits(props.get("GEOID", ""))

                # Standardize lengths
                if st: st = st.zfill(2)
                if co: co = co.zfill(3)
                if tr: tr = tr.zfill(6)
                if bg: bg = bg[:1]  # block group = 1 digit

                # Fix missing components from GEOID if needed
                if geoid and len(geoid) >= 12:
                    st = st or geoid[0:2]
                    co = co or geoid[2:5]
                    tr = tr or geoid[5:11]
                    bg = bg or geoid[11:12]

                # Validate
                if not (st and co and tr and bg):
                    continue
                if not (len(st) == 2 and len(co) == 3 and len(tr) == 6 and len(bg) == 1):
                    continue

                if not geoid:
                    geoid = f"{st}{co}{tr}{bg}"

                records.append({
                    "GEOID": geoid,
                    "STATE": st,
                    "COUNTY": co,
                    "TRACT": tr,
                    "BLOCK_GROUP": bg,
                    "wkt": wkt
                })

                total_kept += 1
                county_total += 1

            if got < params["resultRecordCount"]:
                break

            offset += got

        print(f"  ✔ Kept {county_total} geometries for county {county}")
        print(f"Running total = {total_kept}\n")

        print(f"Final total block groups downloaded: {total_kept}")
        # Convert collected records (list of dicts) to a DataFrame so that
        # downstream code can treat this like other tabular data and call .to_csv()
        if not records:
            # Return an empty DataFrame with the expected columns if no records
            return pd.DataFrame(
                columns=["GEOID", "STATE", "COUNTY", "TRACT", "BLOCK_GROUP", "wkt"]
            )

        return pd.DataFrame(records)

    def geojson_to_wkt(geom):
        """
        Convert a minimal GeoJSON geometry to WKT (Polygon/MultiPolygon) without external libs.
        Assumes coordinates are in lon/lat (EPSG:4326).
        """
        if not geom:
            return None
    gtype = geom.get("type")
    coords = geom.get("coordinates")

    def xy_tuple(pt):
        # Accept [x,y] or [x,y,z]
        try:
            x, y = pt[0], pt[1]
            return x, y
        except Exception:
            return None

    if gtype == "Polygon":
        rings = []
        for ring in coords or []:
            pts = []
            for pt in ring:
                xy = xy_tuple(pt)
                if xy is None:
                    continue
                x, y = xy
                pts.append(f"{x} {y}")
            if not pts:
                continue
            rings.append("(" + ", ".join(pts) + ")")
        return "POLYGON(" + ", ".join(rings) + ")" if rings else None
    elif gtype == "MultiPolygon":
        polys = []
        for poly in coords or []:
            rings = []
            for ring in poly:
                pts = []
                for pt in ring:
                    xy = xy_tuple(pt)
                    if xy is None:
                        continue
                    x, y = xy
                    pts.append(f"{x} {y}")
                if not pts:
                    continue
                rings.append("(" + ", ".join(pts) + ")")
            if rings:
                polys.append("(" + ", ".join(rings) + ")")
        return "MULTIPOLYGON(" + ", ".join(polys) + ")" if polys else None
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

    geom_only = "--geom-only" in sys.argv

    if not geom_only:
        # 1) Data tables
        for table, label in tables.items():
            print(f"Downloading {table} ({label}) ...")
            df = fetch_table(table)
            save_csv(df, f"ARC_{label}_2023_BG.csv")
    else:
        print("Skipping ACS tables (geom-only mode).")

    # 2) Geometries
    geom_df = fetch_blockgroup_geometries()
    save_csv(geom_df, "ARC_BG_Geometries_2023.csv")

    # 3) Emit PostGIS loading instructions (prints to console)
    db_url = os.environ.get("POSTGRES_URL", "")
    to_postgis_instructions(db_url or "<postgresql://user:pass@host:port/dbname>", schema="public")

    print("Done.")
