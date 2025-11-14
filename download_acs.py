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

def fetch_blockgroup_geometries():
    """
    Download TIGER/Line 2023 block group polygons for specified counties as GeoJSON
    via the TIGERweb MapServer identify endpoint (per-county), then flatten to a table
    with WKT geometry for easy PostGIS copy.
    """
    # Layer 10 = Census Block Groups
    base = "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/Tracts_Blocks/MapServer/10/query"

    records = []
    total_kept = 0

    for county in arc_counties:
        # Use fields that exist on layer 10: STATE and COUNTY
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
        print(f"Downloading geometry for county {county} ...")
        # Pagination loop
        offset = 0
        page_total = 0
        while True:
            params["resultOffset"] = offset
            try:
                resp = requests.get(base, params=params, timeout=60)
            except Exception as ex:
                print(f"  Request error for county {county} (offset {offset}): {ex}")
                break

            if resp.status_code != 200:
                print(f"  Geometry HTTP error {resp.status_code} (offset {offset})")
                try:
                    errj = resp.json()
                    if isinstance(errj, dict) and "error" in errj:
                        e = errj["error"]
                        print(f"    ArcGIS error code={e.get('code')} message={e.get('message')}")
                        if e.get("details"):
                            print(f"  details: {e['details']}")
                    else:
                        print(f"    body (json): {errj}")
                except Exception:
                    print(f"    body (text): {resp.text[:300]}")
                break

            try:
                gj = resp.json()
            except Exception as ex:
                print(f"  Geometry parse error (offset {offset}): {ex}; body: {resp.text[:300]}")
                break

            if isinstance(gj, dict) and "error" in gj:
                e = gj["error"]
                print(f"  ArcGIS payload error code={e.get('code')} message={e.get('message')} (offset {offset})")
                if e.get("details"):
                    print(f"  details: {e['details']}")
                break

            feats = gj.get("features", [])
            got = len(feats)
            print(f"  features returned: {got} (offset {offset})")
            if not feats:
                # No more pages
                break

            sample_props = feats[0].get("properties") or {}
            if sample_props and offset == 0:
                print(f"  sample keys: {sorted(list(sample_props.keys()))[:10]}")

            for feat in feats:
                props = feat.get("properties") or {}
                geom = feat.get("geometry")
                if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
                    continue

                wkt = geojson_to_wkt(geom)
                if not wkt:
                    continue

                geoid = str(
                    props.get("GEOID")
                    or props.get("GEOID10")
                    or props.get("BG_GEOID")
                    or ""
                ).strip()

                # On layer 10 the fields are STATE, COUNTY, TRACT, BLOCK_GROUP
                st = (props.get("STATE") or "").strip()
                co = (props.get("COUNTY") or "").strip()
                tr = (props.get("TRACT") or "").strip()
                bg = (props.get("BLOCK_GROUP") or "").strip()

                # Normalize components safely
                def digits(s: str) -> str:
                    return "".join(ch for ch in s if ch.isdigit())

                # State and county should be 2 and 3 digits
                st_d = digits(st)
                co_d = digits(co)
                if st_d:
                    st = st_d.zfill(2)
                if co_d:
                    co = co_d.zfill(3)

                # Tract must be 6-digit numeric string
                tr_d = digits(tr)
                if tr_d:
                    tr = tr_d.zfill(6)

                # Block group must be 1 digit
                bg_d = digits(bg)
                if bg_d:
                    bg = bg_d[:1]

                # If components missing, derive from GEOID digits
                if (not st or not co or not tr or not bg) and geoid:
                    g = digits(geoid)
                    if len(g) >= 12:
                        st = st or g[0:2]
                        co = co or g[2:5]
                        tr = tr or g[5:11]
                        bg = bg or g[11:12]

                # Final validation: exact lengths required
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
                page_total += 1

            # Next page
            if got < params["resultRecordCount"]:
                # Last page reached
                break
            offset += got

        print(f"  Total geometries kept for county {county}: {page_total}")
        print(f"Running total geometries kept: {total_kept}")

    gdf = pd.DataFrame.from_records(records)
    if gdf.empty:
        print("No rows made it into the output after filtering.")
        gdf = pd.DataFrame(columns=["GEOID","STATE","COUNTY","TRACT","BLOCK_GROUP","wkt"])

    gdf.rename(columns={
        "STATE": "state",
        "COUNTY": "county",
        "TRACT": "tract",
        "BLOCK_GROUP": "block group"
    }, inplace=True)

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