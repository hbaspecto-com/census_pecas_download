import requests
import json
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

def make_tract_geoid(df):
    # 11-digit tract GEOID: SSCCCTTTTTT
    return (df["state"] + df["county"] + df["tract"])

def fetch_table(table, geoid_list=None):
    """
    Fetch ACS table data for block groups.
    
    Args:
        table: ACS table name (e.g., "B25024")
        geoid_list: Optional list of GEOIDs to fetch data for. If provided, only these
                    block groups will be fetched. If None, fetches all block groups in arc_counties.
    
    Returns:
        DataFrame with GEOID and ACS variables
    """
    vars_all = get_variables(table)
    rows = []
    
    # If geoid_list provided, organize by county for efficient querying
    if geoid_list is not None:
        # Group GEOIDs by county
        county_bgs = {}
        for geoid in geoid_list:
            if len(geoid) >= 5:
                county_code = geoid[2:5]
                if county_code not in county_bgs:
                    county_bgs[county_code] = []
                # Extract tract and block group
                if len(geoid) >= 12:
                    tract = geoid[5:11]
                    bg = geoid[11:12]
                    county_bgs[county_code].append((tract, bg))
        
        counties_to_fetch = list(county_bgs.keys())
    else:
        counties_to_fetch = arc_counties
        county_bgs = None

    for county in counties_to_fetch:
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
        if df_chunks:
            df_merged = df_chunks[0]
            for part in df_chunks[1:]:
                df_merged = df_merged.merge(
                    part.drop(columns=["NAME"]),
                    on=["state","county","tract","block group"],
                    how="left"
                )

            # If geoid_list provided, filter to only those block groups
            if county_bgs is not None and county in county_bgs:
                df_merged["temp_geoid"] = make_geoid(df_merged)
                target_geoids = [f"{state}{county}{tract}{bg}" for tract, bg in county_bgs[county]]
                df_merged = df_merged[df_merged["temp_geoid"].isin(target_geoids)]
                df_merged = df_merged.drop(columns=["temp_geoid"])

            rows.append(df_merged)

    if not rows:
        return pd.DataFrame()
    
    out = pd.concat(rows, ignore_index=True)
    out["GEOID"] = make_geoid(out)
    # Optional: reorder GEOID first
    cols = ["GEOID","NAME","state","county","tract","block group"] + [c for c in out.columns if c not in {"GEOID","NAME","state","county","tract","block group"}]
    return out[cols]

def fetch_tract_table(table, arc_counties_list=None, state_code=None):
    """
    Fetch ACS table data for census tracts within ARC counties.

    Args:
        table: ACS table/group name (e.g., "B11001")
        arc_counties_list: list of 3-digit county FIPS in the target state
        state_code: 2-digit state FIPS string

    Returns:
        DataFrame with GEOID (tract), geography keys, and variables
    """
    if arc_counties_list is None:
        arc_counties_list = arc_counties
    if state_code is None:
        state_code = state

    vars_all = get_variables(table)
    rows = []

    for county in arc_counties_list:
        print(f"  County {county} (tracts)...")
        df_chunks = []
        for var_chunk in chunk(vars_all, 20):
            vars_str = ",".join(var_chunk)
            url = (
                f"https://api.census.gov/data/2023/acs/acs5?"
                f"get=NAME,{vars_str}&"
                f"for=tract:*&"
                f"in=state:{state_code}%20county:{county}"
            )
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
                    break
                except Exception as e:
                    print(f"    Error on attempt {attempt+1}: {e}")
                    time.sleep(2)
        if df_chunks:
            df_merged = df_chunks[0]
            for part in df_chunks[1:]:
                df_merged = df_merged.merge(
                    part.drop(columns=["NAME"]),
                    on=["state","county","tract"],
                    how="left"
                )
            rows.append(df_merged)

    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out["GEOID"] = make_tract_geoid(out)
    cols = ["GEOID","NAME","state","county","tract"] + [c for c in out.columns if c not in {"GEOID","NAME","state","county","tract"}]
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
        "TIGERweb/tigerWMS_ACS2023/MapServer/10/query"
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
                    print(f"  Skipping unsupported geometry type: {geom.get('type') if geom else 'None'}")
                    continue

                # Use the top-level helper
                wkt = geojson_to_wkt(geom)
                if not wkt:
                    print(f"  Skipping unsupported geometry: {geom}")
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
                    print(f"  Skipping invalid GEOID: {geoid} since {st} {co} {tr} {bg} are missing")
                    continue
                if not (len(st) == 2 and len(co) == 3 and len(tr) == 6 and len(bg) == 1):
                    print(f"  Skipping invalid GEOID: {geoid} since {st}, {co}, {tr}, {bg} are wrong length")
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

    # After all counties are processed
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

    out_file = os.path.join(download_dir, path)
    df.to_csv(out_file, index=False)

def compare_geoids(geom_geoids, data_geoids, table_label):
    """
    Compare GEOIDs between geometry and data tables and report mismatches.
    
    Args:
        geom_geoids: Set or list of GEOIDs from geometry data
        data_geoids: Set or list of GEOIDs from table data
        table_label: Label for the table being compared (for reporting)
    
    Returns:
        dict with 'in_geom_not_data' and 'in_data_not_geom' lists
    """
    geom_set = set(geom_geoids)
    data_set = set(data_geoids)
    
    in_geom_not_data = sorted(geom_set - data_set)
    in_data_not_geom = sorted(data_set - geom_set)
    
    print(f"\n  GEOID Comparison for {table_label}:")
    print(f"    Block groups in geometry: {len(geom_set)}")
    print(f"    Block groups in data: {len(data_set)}")
    print(f"    In geometry but NOT in data: {len(in_geom_not_data)}")
    if in_geom_not_data:
        print(f"      (Possible data suppression or missing data)")
        if len(in_geom_not_data) <= 10:
            print(f"      GEOIDs: {in_geom_not_data}")
        else:
            print(f"      First 10 GEOIDs: {in_geom_not_data[:10]}")
    print(f"    In data but NOT in geometry: {len(in_data_not_geom)}")
    if in_data_not_geom:
        print(f"      (Unexpected - should investigate)")
        if len(in_data_not_geom) <= 10:
            print(f"      GEOIDs: {in_data_not_geom}")
        else:
            print(f"      First 10 GEOIDs: {in_data_not_geom[:10]}")
    
    return {
        'in_geom_not_data': in_geom_not_data,
        'in_data_not_geom': in_data_not_geom
    }

# Download and save all tables


if __name__ == "__main__":
    os.makedirs(".", exist_ok=True)

    geom_only = "--geom-only" in sys.argv
    tract_households = "--tract-households" in sys.argv
    tract_households_with_taz = "--tract-households-with-taz" in sys.argv
    tract_households_base = "--tract-households-base" in sys.argv

    download_dir = "downloads"
    os.makedirs(download_dir, exist_ok=True)

    # Optional: If only tract households are requested, we can skip geometry download
    if not tract_households and not tract_households_with_taz and not tract_households_base:
        # 1) First, download geometries to get the definitive list of block groups
        print("Downloading block group geometries...")
        geom_df = fetch_blockgroup_geometries(state = state, arc_counties = arc_counties)
        save_csv(geom_df, "ARC_BG_Geometries_2023.csv")
        
        # Extract the list of GEOIDs from geometries
        geoid_list = geom_df["GEOID"].tolist() if not geom_df.empty else []
        print(f"Found {len(geoid_list)} block groups from geometry download.")
    else:
        geoid_list = []

    def _save_tract_households(df, add_taz=False):
        """
        Internal helper to save tract households CSV, optionally with TAZ list merged in.
        When add_taz=True, fetch TAZ list per tract and add a column `TAZ_list` (comma-separated TAZ GEOIDs).
        """
        if df.empty:
            print("No tract data returned.")
            return
        # Keep total households estimate and MOE if present
        keep_cols = [c for c in df.columns if c in {"GEOID","NAME","state","county","tract","B11001_001E","B11001_001M"}]
        if "B11001_001E" not in df.columns:
            print("Warning: B11001_001E not found in response. Saving all variables instead.")
            out_df = df
        else:
            out_df = df[keep_cols]

        if add_taz:
            print("Fetching TAZ membership for tracts using TIGERweb (TAZ centroid-in-tract)...")

            def fetch_taz_by_tract(arc_counties_list=None, state_code=None):
                """
                Build TAZ -> tract membership using TIGERweb services via centroid-in-tract rule.

                Steps per county:
                  1) Query TAZ layer (Census 2020 Traffic Analysis Zones) filtering by state+county,
                     requesting centroids for each TAZ.
                  2) For each centroid point, query the Tracts layer (ACS 2023 geography) to find
                     the containing tract and record mapping TRACT_GEOID -> TAZ_GEOID.

                Returns DataFrame with columns: TRACT_GEOID, TAZ_GEOID
                """
                if arc_counties_list is None:
                    arc_counties_list = arc_counties
                if state_code is None:
                    state_code = state

                # TIGERweb endpoints
                # Resolve the correct TAZ service endpoint dynamically (service name differs by vintage)
                TAZ_CANDIDATE_URLS = [
                    # Common current service
                    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Traffic_Analysis_Zones/MapServer/0/query",
                    # Vintage-specific variants
                    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Traffic_Analysis_Zones_2020/MapServer/0/query",
                    # Older guess (may 404)
                    "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/Traffic_Analysis_Zones/MapServer/0/query",
                ]
                # We will resolve the correct tracts layer id dynamically (9 is typical, but varies)
                TRACTS_BASE = (
                    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
                    "TIGERweb/tigerWMS_ACS2023/MapServer"
                )
                TRACTS_CANDIDATE_LAYERS = [9, 8, 7, 6, 5]

                def _request_with_retry(url, params, max_attempts=5, pause=2):
                    for attempt in range(max_attempts):
                        try:
                            r = requests.get(url, params=params, timeout=40)
                            if r.status_code == 200:
                                return r.json()
                            else:
                                print(f"    HTTP {r.status_code}: {r.text[:200]}")
                        except Exception as e:
                            print(f"    Request error (attempt {attempt+1}): {e}")
                        time.sleep(pause)
                    return None

                results = []

                def field_first(attrs, names, default=None):
                    for n in names:
                        if n in attrs and attrs[n] is not None:
                            return attrs[n]
                    return default

                # Pick a working TAZ query URL by probing candidates
                def resolve_taz_query_url():
                    test_params = {"where": "1=1", "outFields": "*", "f": "json", "returnGeometry": "false", "resultRecordCount": 1}
                    for url in TAZ_CANDIDATE_URLS:
                        jd = _request_with_retry(url, test_params)
                        if jd and (jd.get("features") is not None or jd.get("error") is None):
                            # ArcGIS responds with a JSON that includes features or at least no 404 HTML
                            if jd.get("features"):
                                return url
                    return None

                TAZ_QUERY = resolve_taz_query_url()
                if not TAZ_QUERY:
                    print("    Error: Could not resolve a working TAZ service on TIGERweb; TAZ listing will be empty.")
                    return pd.DataFrame(columns=["TRACT_GEOID","TAZ_GEOID"])

                # Detect a working tracts layer and usable field names
                def resolve_tracts_layer():
                    for lid in TRACTS_CANDIDATE_LAYERS:
                        url = f"{TRACTS_BASE}/{lid}/query"
                        # Try STATEFP first
                        for where in (f"STATEFP = '{state_code}'", f"STATE = '{state_code}'", "1=1"):
                            params = {
                                "where": where,
                                "outFields": "*",
                                "f": "json",
                                "returnGeometry": "false",
                                "resultRecordCount": 1
                            }
                            jd = _request_with_retry(url, params)
                            if jd and jd.get("features"):
                                attrs = jd["features"][0]["attributes"]
                                # Determine likely field names
                                state_field = "STATEFP" if "STATEFP" in attrs else ("STATE" if "STATE" in attrs else None)
                                county_field = "COUNTYFP" if "COUNTYFP" in attrs else ("COUNTY" if "COUNTY" in attrs else None)
                                tract_field = "TRACTCE" if "TRACTCE" in attrs else ("TRACT" if "TRACT" in attrs else None)
                                geoid_field = "GEOID" if "GEOID" in attrs else ("GEOID20" if "GEOID20" in attrs else None)
                                return {
                                    "layer_id": lid,
                                    "url": url,
                                    "state_field": state_field,
                                    "county_field": county_field,
                                    "tract_field": tract_field,
                                    "geoid_field": geoid_field
                                }
                    return None

                tracts_meta = resolve_tracts_layer()
                if not tracts_meta:
                    print("    Error: Could not resolve a working Tracts layer on TIGERweb; TAZ listing will be empty.")
                    return pd.DataFrame(columns=["TRACT_GEOID","TAZ_GEOID"])
                TRACTS_QUERY = tracts_meta["url"]

                for ccc in arc_counties_list:
                    print(f"  County {ccc} (TAZ centroids and tract lookup)...")

                    # 1) Pull all TAZ features for GA, then client-filter by county (robust to field name changes)
                    # Try a sequence of server-side filters; fall back to broader pulls if needed.
                    taz_features = []

                    def pull_taz_features(where_clause=None):
                        params = {
                            "outFields": "*",
                            "f": "json",
                            "returnGeometry": "true",
                            "outSR": 4326,
                            "returnCentroid": "true",
                            "resultOffset": 0,
                            "resultRecordCount": 1000
                        }
                        if where_clause:
                            params["where"] = where_clause
                        else:
                            params["where"] = "1=1"

                        feats_all = []
                        while True:
                            data = _request_with_retry(TAZ_QUERY, params)
                            if not data or "features" not in data:
                                break
                            feats = data.get("features", [])
                            feats_all.extend(feats)
                            got = len(feats)
                            if data.get("exceededTransferLimit") and got > 0:
                                params["resultOffset"] += got
                            else:
                                break
                        return feats_all

                    # Attempt 1: filter by STATEFP/COUNTYFP (quoted)
                    taz_features = pull_taz_features(f"STATEFP = '{state_code}' AND COUNTYFP = '{ccc}'")
                    # Attempt 2: unquoted numeric compare (in case fields are numeric)
                    if not taz_features:
                        taz_features = pull_taz_features(f"STATEFP = {int(state_code)} AND COUNTYFP = {int(ccc)}")
                    # Attempt 3: filter by STATE/COUNTY if previous return 0
                    if not taz_features:
                        taz_features = pull_taz_features(f"STATE = '{state_code}' AND COUNTY = '{ccc}'")
                    # Attempt 3: GA-wide, client-filter county
                    if not taz_features:
                        ga_feats = (
                            pull_taz_features(f"STATEFP = '{state_code}'") or
                            pull_taz_features(f"STATEFP = {int(state_code)}") or
                            pull_taz_features(f"STATE = '{state_code}'") or
                            pull_taz_features(None)
                        )
                        # Client-side filter by county code
                        filtered = []
                        for ft in ga_feats or []:
                            a = ft.get("attributes", {}) or {}
                            county_fields = [
                                "COUNTYFP", "COUNTY", "CNTYFP", "COUNTYFP20", "COUNTYFIPS"
                            ]
                            ok = False
                            for fld in county_fields:
                                val = a.get(fld)
                                if val is not None and str(val).zfill(3) == str(ccc).zfill(3):
                                    ok = True
                                    break
                            if not ok:
                                # As another fallback, check GEOID suffix
                                geoid_val = a.get("GEOID") or a.get("GEOID20")
                                if geoid_val and len(str(geoid_val)) >= 5 and str(geoid_val)[2:5] == str(ccc):
                                    ok = True
                            if ok:
                                filtered.append(ft)
                        taz_features = filtered

                    if not taz_features:
                        print("    No TAZ centroid list available; falling back to tract->TAZ polygon intersects...")
                        # Fallback approach: pull tract polygons for this county, then query TAZ that intersect each tract
                        # 2a) Pull tract polygons
                        sf = tracts_meta.get("state_field") or "STATEFP"
                        cf = tracts_meta.get("county_field") or "COUNTYFP"
                        tract_where = f"{sf} = '{state_code}' AND {cf} = '{ccc}'"
                        tract_params2 = {
                            "where": tract_where,
                            "outFields": "*",
                            "f": "json",
                            "returnGeometry": "true",
                            "outSR": 4326,
                            "resultOffset": 0,
                            "resultRecordCount": 1000
                        }
                        tract_polys = []
                        while True:
                            td = _request_with_retry(TRACTS_QUERY, tract_params2)
                            if not td or "features" not in td:
                                break
                            feats = td.get("features", [])
                            tract_polys.extend(feats)
                            got = len(feats)
                            if td.get("exceededTransferLimit") and got > 0:
                                tract_params2["resultOffset"] += got
                            else:
                                break

                        if not tract_polys:
                            # Try alternative WHERE using STATE/COUNTY
                            tract_params2["where"] = f"STATE = '{state_code}' AND COUNTY = '{ccc}'"
                            while True:
                                td = _request_with_retry(TRACTS_QUERY, tract_params2)
                                if not td or "features" not in td:
                                    break
                                feats = td.get("features", [])
                                tract_polys.extend(feats)
                                got = len(feats)
                                if td.get("exceededTransferLimit") and got > 0:
                                    tract_params2["resultOffset"] += got
                                else:
                                    break

                        if not tract_polys:
                            print("    Warning: Could not retrieve tract polygons for fallback; continuing to next county.")
                            # As a debugging aid, try printing a sample of available fields
                            sample = _request_with_retry(TRACTS_QUERY, {"where": "1=1", "outFields": "*", "f": "json", "returnGeometry": "false", "resultRecordCount": 1})
                            if sample and sample.get("features"):
                                print("    Tracts sample fields:", list(sample["features"][0]["attributes"].keys()))
                            continue

                        # 2b) For each tract polygon, get intersecting TAZ features
                        for tft in tract_polys:
                            t_attrs2 = tft.get("attributes", {})
                            tract_geoid2 = field_first(t_attrs2, [tracts_meta.get("geoid_field") or "GEOID", "GEOID20"]) or ""
                            if not tract_geoid2:
                                s2 = field_first(t_attrs2, [tracts_meta.get("state_field") or "STATEFP", "STATE"]) or ''
                                c2 = field_first(t_attrs2, [tracts_meta.get("county_field") or "COUNTYFP", "COUNTY"]) or ''
                                tc2 = field_first(t_attrs2, [tracts_meta.get("tract_field") or "TRACTCE", "TRACT"]) or ''
                                tract_geoid2 = f"{str(s2)}{str(c2)}{str(tc2)}"
                            geom2 = tft.get("geometry")
                            if not geom2:
                                continue
                            # Construct polygon geometry JSON for query
                            poly_geom = {
                                "rings": geom2.get("rings", []),
                                "spatialReference": {"wkid": 4326}
                            }
                            try:
                                geom_str = json.dumps(poly_geom)
                            except Exception:
                                continue
                            taz_q_params = {
                                "geometry": geom_str,
                                "geometryType": "esriGeometryPolygon",
                                "inSR": 4326,
                                "spatialRel": "esriSpatialRelIntersects",
                                "outFields": "GEOID,GEOID20,STATEFP,COUNTYFP,TAZ,TAZCE",
                                "returnGeometry": "false",
                                "f": "json"
                            }
                            tz = _request_with_retry(TAZ_QUERY, taz_q_params)
                            if not tz or not tz.get("features"):
                                continue
                            for tzf in tz.get("features", []):
                                a = tzf.get("attributes", {})
                                taz_geoid2 = a.get("GEOID") or a.get("GEOID20")
                                if not taz_geoid2:
                                    taz_id2 = a.get("TAZ") or a.get("TAZCE")
                                    if taz_id2 is None:
                                        continue
                                    taz_geoid2 = f"{state_code}{ccc}{str(taz_id2)}"
                                results.append({"TRACT_GEOID": tract_geoid2, "TAZ_GEOID": taz_geoid2})
                        # Done with fallback for this county
                        continue

                    # 2) For each TAZ centroid, find containing tract
                    for ftr in taz_features:
                        attrs = ftr.get("attributes", {})
                        # Prefer GEOID if present; else build from STATE+COUNTY+TAZ (ID field may be 'TAZ')
                        taz_geoid = attrs.get("GEOID")
                        if not taz_geoid:
                            taz_id = attrs.get("TAZ") or attrs.get("taz") or attrs.get("TAZCE")
                            if taz_id is None:
                                # As a last resort, skip if we can't identify the TAZ id
                                continue
                            taz_geoid = f"{state_code}{ccc}{str(taz_id)}"

                        centroid = ftr.get("centroid") or {}
                        x = centroid.get("x")
                        y = centroid.get("y")
                        if x is None or y is None:
                            # If centroid missing, optionally fall back to polygon's first coordinate
                            geom = ftr.get("geometry") or {}
                            # Attempt to grab a coordinate if polygon exists (rings[0][0])
                            try:
                                x, y = geom["rings"][0][0]
                            except Exception:
                                continue

                        tract_params = {
                            "geometry": f"{x},{y}",
                            "geometryType": "esriGeometryPoint",
                            "inSR": 4326,
                            "spatialRel": "esriSpatialRelIntersects",
                            "outFields": "GEOID,STATEFP,COUNTYFP,TRACTCE,STATE,COUNTY,TRACT",
                            "returnGeometry": "false",
                            "f": "json"
                        }
                        tdata = _request_with_retry(TRACTS_QUERY, tract_params)
                        if not tdata or not tdata.get("features"):
                            continue
                        t_attrs = tdata["features"][0]["attributes"]
                        tract_geoid = t_attrs.get("GEOID")
                        if not tract_geoid:
                            # Build from parts if GEOID is absent
                            s = t_attrs.get('STATEFP') or t_attrs.get('STATE') or ''
                            c = t_attrs.get('COUNTYFP') or t_attrs.get('COUNTY') or ''
                            t = t_attrs.get('TRACTCE') or t_attrs.get('TRACT') or ''
                            tract_geoid = f"{str(s)}{str(c)}{str(t)}"
                        results.append({"TRACT_GEOID": tract_geoid, "TAZ_GEOID": taz_geoid})

                if not results:
                    return pd.DataFrame(columns=["TRACT_GEOID","TAZ_GEOID"])
                return pd.DataFrame(results)

            taz_df = fetch_taz_by_tract(arc_counties_list=arc_counties, state_code=state)
            if taz_df.empty:
                print("Warning: No TAZ data could be fetched; saving households without TAZ list.")
            else:
                # Aggregate to comma-separated unique list per tract
                agg = (
                    taz_df.dropna(subset=["TRACT_GEOID","TAZ_GEOID"])\
                          .groupby("TRACT_GEOID")["TAZ_GEOID"]
                          .apply(lambda s: ",".join(sorted(pd.unique(s.tolist()))))
                          .reset_index()
                          .rename(columns={"TAZ_GEOID":"TAZ_list"})
                )
                out_df = out_df.merge(agg, left_on="GEOID", right_on="TRACT_GEOID", how="left")
                out_df = out_df.drop(columns=[c for c in ["TRACT_GEOID"] if c in out_df.columns])

        save_csv(out_df, "ARC_TotalHouseholds_2023_Tract.csv")
        print(f"  Saved tract households to {os.path.join(download_dir, 'ARC_TotalHouseholds_2023_Tract.csv')}")
        print(f"  Rows: {len(out_df)}")

    if tract_households_base:
        # Roll up tract-level households to base tract (first 4 digits of TRACTCE, e.g., 1801)
        print("Downloading tract-level total households (B11001) for ARC counties...")
        tract_df = fetch_tract_table("B11001", arc_counties_list=arc_counties, state_code=state)
        if tract_df.empty:
            print("No tract data returned.")
        else:
            # Ensure numeric types for estimate and MOE
            if "B11001_001E" in tract_df.columns:
                tract_df["B11001_001E"] = pd.to_numeric(tract_df["B11001_001E"], errors="coerce")
            if "B11001_001M" in tract_df.columns:
                tract_df["B11001_001M"] = pd.to_numeric(tract_df["B11001_001M"], errors="coerce")

            # Base tract = first 4 chars of the 6-digit TRACTCE string provided by ACS API in column 'tract'
            # The ACS API returns zero-padded strings already.
            tract_df["tract_base"] = tract_df["tract"].astype(str).str[:4]

            grp_keys = ["state", "county", "tract_base"]

            # Sum estimates
            agg_dict = {"B11001_001E": "sum"}
            has_moe = "B11001_001M" in tract_df.columns
            if has_moe:
                # For MOE, combine using root-sum-of-squares across component tracts
                tract_df["_MOE2"] = tract_df["B11001_001M"] ** 2
                moe_sq = tract_df.groupby(grp_keys)["_MOE2"].sum().rename("_MOE2_sum")

            est_sum = tract_df.groupby(grp_keys)["B11001_001E"].sum().rename("B11001_001E")

            out_df = est_sum.reset_index()
            if has_moe:
                out_df = out_df.merge(moe_sq.reset_index(), on=grp_keys, how="left")
                out_df["B11001_001M"] = (out_df["_MOE2_sum"].clip(lower=0) ** 0.5).round(0)
                out_df = out_df.drop(columns=["_MOE2_sum"]) 

            # Construct a 9-digit base GEOID: state(2) + county(3) + tract_base(4)
            out_df["GEOID_base"] = out_df["state"] + out_df["county"] + out_df["tract_base"]

            # Order columns
            cols = ["GEOID_base", "state", "county", "tract_base", "B11001_001E"]
            if has_moe:
                cols.append("B11001_001M")
            out_df = out_df[cols]

            # Save
            save_csv(out_df, "ARC_TotalHouseholds_2023_TractBase.csv")
            print(f"  Saved base-tract households to {os.path.join(download_dir, 'ARC_TotalHouseholds_2023_TractBase.csv')}")
            print(f"  Rows: {len(out_df)}")

    elif tract_households or tract_households_with_taz:
        # Tract-level total households from B11001
        print("Downloading tract-level total households (B11001) for ARC counties...")
        tract_df = fetch_tract_table("B11001", arc_counties_list=arc_counties, state_code=state)
        _save_tract_households(tract_df, add_taz=tract_households_with_taz)
    elif not geom_only:
        # 2) Data tables - fetch only for the GEOIDs we have geometries for
        all_mismatches = {}
        
        for table, label in tables.items():
            print(f"Downloading {table} ({label}) for {len(geoid_list)} block groups...")
            df = fetch_table(table, geoid_list=geoid_list)
            save_csv(df, f"ARC_{label}_2023_BG.csv")
            print(f"  Downloaded {len(df)} rows for {label}")
            
            # Compare GEOIDs between geometry and table data
            if not df.empty and "GEOID" in df.columns:
                data_geoids = df["GEOID"].tolist()
                mismatches = compare_geoids(geoid_list, data_geoids, label)
                all_mismatches[label] = mismatches
        
        # Save mismatch report to a file
        if all_mismatches:
            print("\nSaving GEOID mismatch report...")
            mismatch_report_path = os.path.join(download_dir, "GEOID_Mismatch_Report.txt")
            with open(mismatch_report_path, 'w') as f:
                f.write("GEOID Mismatch Report\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total block groups in geometry: {len(geoid_list)}\n\n")
                
                for label, mismatches in all_mismatches.items():
                    f.write(f"\n{label} ({tables.get([k for k, v in tables.items() if v == label][0], 'Unknown')})\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"In geometry but NOT in data ({len(mismatches['in_geom_not_data'])} block groups):\n")
                    if mismatches['in_geom_not_data']:
                        f.write("  Note: This may be due to data suppression or missing data\n")
                        for geoid in mismatches['in_geom_not_data']:
                            f.write(f"  {geoid}\n")
                    else:
                        f.write("  None\n")
                    
                    f.write(f"\nIn data but NOT in geometry ({len(mismatches['in_data_not_geom'])} block groups):\n")
                    if mismatches['in_data_not_geom']:
                        f.write("  Note: This is unexpected and should be investigated\n")
                        for geoid in mismatches['in_data_not_geom']:
                            f.write(f"  {geoid}\n")
                    else:
                        f.write("  None\n")
                    f.write("\n")
            
            print(f"Mismatch report saved to: {mismatch_report_path}")
    else:
        print("Skipping ACS tables (geom-only mode).")

    # 3) Emit PostGIS loading instructions (prints to console)
    db_url = os.environ.get("POSTGRES_URL", "")
    #to_postgis_instructions(db_url or "<postgresql://user:pass@host:port/dbname>", schema="public")

    print("Done.")
