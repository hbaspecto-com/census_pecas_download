#!/usr/bin/env python3

"""
run_regression.py

Regression workflow for block-group residential square footage modeling.

Implemented:
- Step 1: Define initial geography (Cobb block groups)
- Step 4: Aggregate residential square footage by block group
- Step 5: Prepare ACS household predictors
"""

from pathlib import Path
import argparse
import pandas as pd
import requests


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

ACS_YEAR = "2024"
ACS_DATASET = "acs/acs5"
STATE_FIPS = "13"

COBB_COUNTY_FIPS = "067"

ARC_COUNTIES = {
    "013": "Barrow",
    "015": "Bartow",
    "035": "Butts",
    "045": "Carroll",
    "057": "Cherokee",
    "063": "Clayton",
    "067": "Cobb",
    "077": "Coweta",
    "085": "Dawson",
    "089": "DeKalb",
    "097": "Douglas",
    "113": "Fayette",
    "117": "Forsyth",
    "121": "Fulton",
    "135": "Gwinnett",
    "143": "Haralson",
    "151": "Henry",
    "159": "Jasper",
    "217": "Newton",
    "223": "Paulding",
    "247": "Rockdale",
}

OUTPUT_DIR = Path("outputs")

# Step 3 input (export from parcel->BG assignment workflow)
STEP3_ASSIGNMENT_CSV = OUTPUT_DIR / "arc_parcel_bg_assignment_2024.csv"

# Step 1 output
STEP1_COBB_BG_CSV = OUTPUT_DIR / "block_groups_cobb_2024.csv"

# Step 4 outputs (Cobb)
STEP4_COBB_BG_RES_SQFT_CSV = OUTPUT_DIR / "regression_bg_res_sqft_cobb_2024.csv"
STEP4_COBB_QA_TXT = OUTPUT_DIR / "qa_step4_cobb_2024.txt"
STEP4_COBB_UNMATCHED_CSV = OUTPUT_DIR / "regression_unmatched_parcels_cobb_2024.csv"

# Step 5 outputs (Cobb ACS predictors)
STEP5_COBB_ACS_PREDICTORS_CSV = OUTPUT_DIR / "regression_acs_predictors_cobb_2024.csv"
STEP5_COBB_QA_TXT = OUTPUT_DIR / "qa_step5_acs_cobb_2024.txt"


# ---------------------------------------------------------------------
# Geography helpers (Step 1)
# ---------------------------------------------------------------------

def make_block_group_geoid(df: pd.DataFrame) -> pd.Series:
    """
    Build 12-digit block group GEOID from Census API geography columns.

    GEOID = state + county + tract + block group
    """
    return (
        df["state"].astype(str).str.zfill(2)
        + df["county"].astype(str).str.zfill(3)
        + df["tract"].astype(str).str.zfill(6)
        + df["block group"].astype(str).str.zfill(1)
    )


def fetch_block_groups_for_county(
    state_fips: str,
    county_fips: str,
    county_name: str,
    acs_year: str = ACS_YEAR,
) -> pd.DataFrame:
    """
    Fetch block group geography rows for one county from ACS 5-year Detailed Tables.

    The Census API requires at least one data variable. We request B11016_001E.
    """
    url = f"https://api.census.gov/data/{acs_year}/{ACS_DATASET}"

    params = {
        "get": "NAME,B11016_001E",
        "for": "block group:*",
        "in": f"state:{state_fips} county:{county_fips}",
    }

    response = requests.get(url, params=params, timeout=60)

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch ACS block groups for county {county_fips}. "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

    data = response.json()
    df = pd.DataFrame(data[1:], columns=data[0])

    df["GEOID"] = make_block_group_geoid(df)
    df["county_name"] = county_name
    df["acs_year"] = acs_year

    cols = [
        "GEOID",
        "NAME",
        "state",
        "county",
        "county_name",
        "tract",
        "block group",
        "acs_year",
        "B11016_001E",
    ]

    return df[cols].sort_values("GEOID").reset_index(drop=True)


def fetch_block_groups_for_counties(counties: dict[str, str]) -> pd.DataFrame:
    """
    Fetch block group geography rows for multiple counties.
    """
    frames = []

    for county_fips, county_name in counties.items():
        print(f"Fetching block groups for {county_name} County ({county_fips})...")
        county_df = fetch_block_groups_for_county(
            state_fips=STATE_FIPS,
            county_fips=county_fips,
            county_name=county_name,
        )
        frames.append(county_df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------
# Shared QA helpers
# ---------------------------------------------------------------------

def save_qa_report(lines: list[str], path: Path) -> None:
    """
    Save QA report lines to a text file.
    """
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def geography_qa(df: pd.DataFrame, expected_counties: set[str]) -> list[str]:
    """
    Run basic geography QA checks and return report lines.
    """
    lines = []

    lines.append("Geography QA Report")
    lines.append("=" * 80)
    lines.append(f"ACS year: {ACS_YEAR}")
    lines.append(f"Rows: {len(df):,}")
    lines.append("")

    if df.empty:
        lines.append("ERROR: Geography table is empty.")
        return lines

    duplicate_geoids = df[df["GEOID"].duplicated(keep=False)]["GEOID"].unique()
    bad_geoid_length = df[df["GEOID"].astype(str).str.len() != 12]

    observed_counties = set(df["county"].astype(str).str.zfill(3).unique())

    lines.append("County summary:")
    county_summary = (
        df.groupby(["county", "county_name"])
        .size()
        .reset_index(name="block_group_count")
        .sort_values("county")
    )

    for _, row in county_summary.iterrows():
        lines.append(
            f"  {row['county']} {row['county_name']}: "
            f"{row['block_group_count']:,} block groups"
        )

    lines.append("")

    lines.append(
        "PASS: No duplicate GEOIDs." if len(duplicate_geoids) == 0
        else f"FAIL: Found {len(duplicate_geoids):,} duplicate GEOIDs."
    )
    lines.append(
        "PASS: All GEOIDs are 12 characters." if bad_geoid_length.empty
        else f"FAIL: Found {len(bad_geoid_length):,} GEOIDs not 12 characters."
    )

    missing_counties = expected_counties - observed_counties
    extra_counties = observed_counties - expected_counties

    lines.append(
        "PASS: No expected counties are missing."
        if not missing_counties else f"FAIL: Missing expected counties: {sorted(missing_counties)}"
    )
    lines.append(
        "PASS: No unexpected counties are present."
        if not extra_counties else f"FAIL: Unexpected counties present: {sorted(extra_counties)}"
    )

    lines.append("")

    if expected_counties == {COBB_COUNTY_FIPS}:
        non_cobb_geoids = df[~df["GEOID"].astype(str).str.startswith("13067")]
        lines.append(
            "PASS: All Cobb GEOIDs start with 13067."
            if non_cobb_geoids.empty
            else f"FAIL: Found {len(non_cobb_geoids):,} rows with GEOID not starting 13067."
        )

    return lines


# ---------------------------------------------------------------------
# Step 1 runner
# ---------------------------------------------------------------------

def run_step_1_cobb() -> None:
    """
    Step 1: Fetch and QA Cobb County block group geography.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    counties = {COBB_COUNTY_FIPS: ARC_COUNTIES[COBB_COUNTY_FIPS]}
    bg_df = fetch_block_groups_for_counties(counties)

    output_csv = STEP1_COBB_BG_CSV
    qa_txt = OUTPUT_DIR / "geography_qa_cobb_2024.txt"

    bg_df.to_csv(output_csv, index=False)

    qa_lines = geography_qa(bg_df, expected_counties=set(counties.keys()))
    save_qa_report(qa_lines, qa_txt)

    print(f"Saved block group geography to: {output_csv}")
    print(f"Saved geography QA report to: {qa_txt}")


# ---------------------------------------------------------------------
# Step 4 helpers
# ---------------------------------------------------------------------

def _normalize_geoid(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def _load_cobb_block_groups_for_step4() -> pd.DataFrame:
    """
    Load Cobb block groups from Step 1 output.
    If missing, fetch from ACS and persist first.
    """
    if STEP1_COBB_BG_CSV.exists():
        df_bg = pd.read_csv(STEP1_COBB_BG_CSV, dtype=str)
    else:
        print("Cobb block group file not found. Running Step 1 automatically...")
        run_step_1_cobb()
        df_bg = pd.read_csv(STEP1_COBB_BG_CSV, dtype=str)

    df_bg["GEOID"] = _normalize_geoid(df_bg["GEOID"])
    df_bg["county"] = df_bg["county"].astype(str).str.zfill(3)

    df_bg = df_bg[df_bg["county"] == COBB_COUNTY_FIPS].copy()

    keep_cols = ["GEOID", "state", "county", "tract", "block group", "county_name"]
    keep_cols = [c for c in keep_cols if c in df_bg.columns]
    return df_bg[keep_cols].drop_duplicates(subset=["GEOID"]).sort_values("GEOID").reset_index(drop=True)


def _load_step3_assignment() -> pd.DataFrame:
    """
    Load Step 3 parcel assignment CSV and enforce expected types.
    """
    if not STEP3_ASSIGNMENT_CSV.exists():
        raise FileNotFoundError(
            f"Missing Step 3 assignment file: {STEP3_ASSIGNMENT_CSV}\n"
            "Expected CSV with at least columns: arcid_mr, county_fips, geoid, res_sqft"
        )

    df = pd.read_csv(STEP3_ASSIGNMENT_CSV, dtype=str)

    required = {"arcid_mr", "county_fips", "geoid", "res_sqft"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {STEP3_ASSIGNMENT_CSV}: {sorted(missing)}")

    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    df["geoid"] = _normalize_geoid(df["geoid"])
    df["res_sqft"] = pd.to_numeric(df["res_sqft"], errors="coerce")

    return df


def _aggregate_cobb_res_sqft(
    df_assign: pd.DataFrame,
    df_cobb_bg: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Build Step 4 Cobb block-group aggregation.
    Returns:
      - aggregated block-group DataFrame
      - unmatched Cobb parcel rows
      - summary metrics dict
    """
    county_prefix = f"{STATE_FIPS}{COBB_COUNTY_FIPS}"

    df_cobb = df_assign[df_assign["county_fips"] == COBB_COUNTY_FIPS].copy()

    geoid_len_ok = df_cobb["geoid"].str.len() == 12
    geoid_prefix_ok = df_cobb["geoid"].str.startswith(county_prefix)
    geoid_valid = df_cobb["geoid"].notna() & geoid_len_ok & geoid_prefix_ok

    df_unmatched = df_cobb[~geoid_valid].copy()
    df_matched = df_cobb[geoid_valid].copy()

    df_matched["res_sqft_nonnull"] = df_matched["res_sqft"].fillna(0)

    grouped = (
        df_matched.groupby("geoid", as_index=False)
        .agg(
            residential_record_count=("arcid_mr", "count"),
            total_res_sqft=("res_sqft_nonnull", "sum"),
            zero_res_sqft_record_count=("res_sqft", lambda s: int((s == 0).sum())),
            missing_res_sqft_record_count=("res_sqft", lambda s: int(s.isna().sum())),
        )
        .rename(columns={"geoid": "GEOID"})
    )

    out = df_cobb_bg.merge(grouped, on="GEOID", how="left")

    fill_zero_cols = [
        "residential_record_count",
        "total_res_sqft",
        "zero_res_sqft_record_count",
        "missing_res_sqft_record_count",
    ]
    for col in fill_zero_cols:
        out[col] = out[col].fillna(0)

    out["residential_record_count"] = out["residential_record_count"].astype(int)
    out["total_res_sqft"] = out["total_res_sqft"].round(0).astype("int64")
    out["zero_res_sqft_record_count"] = out["zero_res_sqft_record_count"].astype(int)
    out["missing_res_sqft_record_count"] = out["missing_res_sqft_record_count"].astype(int)

    out = out.sort_values("GEOID").reset_index(drop=True)

    metrics = {
        "cobb_assignment_records": int(len(df_cobb)),
        "matched_records": int(len(df_matched)),
        "unmatched_records": int(len(df_unmatched)),
        "sum_total_res_sqft": int(out["total_res_sqft"].sum()),
        "sum_residential_record_count": int(out["residential_record_count"].sum()),
        "bg_rows": int(len(out)),
        "bg_with_records": int((out["residential_record_count"] > 0).sum()),
        "bg_zero_records": int((out["residential_record_count"] == 0).sum()),
        "bg_zero_sqft": int((out["total_res_sqft"] == 0).sum()),
    }

    return out, df_unmatched, metrics


def _step4_qa_lines(out_df: pd.DataFrame, unmatched_df: pd.DataFrame, metrics: dict) -> list[str]:
    """
    Build a text QA report for Step 4.
    """
    lines = []
    lines.append("Step 4 QA Report - Cobb Residential SqFt by Block Group")
    lines.append("=" * 80)
    lines.append(f"Cobb assignment records: {metrics['cobb_assignment_records']:,}")
    lines.append(f"Matched parcel records: {metrics['matched_records']:,}")
    lines.append(f"Unmatched parcel records: {metrics['unmatched_records']:,}")
    lines.append("")
    lines.append(f"Block-group rows: {metrics['bg_rows']:,}")
    lines.append(f"Block groups with records: {metrics['bg_with_records']:,}")
    lines.append(f"Block groups with zero records: {metrics['bg_zero_records']:,}")
    lines.append(f"Block groups with zero sqft: {metrics['bg_zero_sqft']:,}")
    lines.append("")
    lines.append(f"Total residential records summed in output: {metrics['sum_residential_record_count']:,}")
    lines.append(f"Total residential sqft summed in output: {metrics['sum_total_res_sqft']:,}")
    lines.append("")

    bad_geoid = out_df[out_df["GEOID"].astype(str).str.len() != 12]
    bad_prefix = out_df[~out_df["GEOID"].astype(str).str.startswith("13067")]

    lines.append("GEOID checks:")
    lines.append(
        "PASS: All output GEOIDs are 12 digits."
        if bad_geoid.empty else f"FAIL: {len(bad_geoid):,} GEOIDs are not 12 digits."
    )
    lines.append(
        "PASS: All output GEOIDs start with 13067."
        if bad_prefix.empty else f"FAIL: {len(bad_prefix):,} GEOIDs do not start with 13067."
    )
    lines.append("")

    top10 = out_df.nlargest(10, "total_res_sqft")[["GEOID", "residential_record_count", "total_res_sqft"]]
    lines.append("Top 10 block groups by total_res_sqft:")
    for _, r in top10.iterrows():
        lines.append(
            f"  {r['GEOID']}: total_res_sqft={int(r['total_res_sqft']):,}, "
            f"residential_record_count={int(r['residential_record_count']):,}"
        )

    lines.append("")
    lines.append(f"Unmatched export rows: {len(unmatched_df):,}")

    return lines


# ---------------------------------------------------------------------
# Step 4 runner
# ---------------------------------------------------------------------

def run_step_4_cobb() -> None:
    """
    Step 4:
    Aggregate residential square footage by block group for Cobb County.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    df_bg = _load_cobb_block_groups_for_step4()
    df_assign = _load_step3_assignment()

    out_df, unmatched_df, metrics = _aggregate_cobb_res_sqft(df_assign, df_bg)

    out_df.to_csv(STEP4_COBB_BG_RES_SQFT_CSV, index=False)

    unmatched_cols = [c for c in [
        "arcid_mr", "apn", "county_fips", "county_name", "source_layer",
        "res_sqft", "geoid", "pecas_resi_tranche_mr", "latitude", "longitude"
    ] if c in unmatched_df.columns]
    unmatched_df[unmatched_cols].to_csv(STEP4_COBB_UNMATCHED_CSV, index=False)

    qa_lines = _step4_qa_lines(out_df, unmatched_df, metrics)
    save_qa_report(qa_lines, STEP4_COBB_QA_TXT)

    print(f"Saved Step 4 table: {STEP4_COBB_BG_RES_SQFT_CSV}")
    print(f"Saved Step 4 QA report: {STEP4_COBB_QA_TXT}")
    print(f"Saved unmatched parcels: {STEP4_COBB_UNMATCHED_CSV}")


# ---------------------------------------------------------------------
# Step 5 helpers
# ---------------------------------------------------------------------

def _fetch_acs_table_for_cobb(group: str, variables: list[str]) -> pd.DataFrame:
    """
    Fetch one ACS group/table for Cobb block groups.
    """
    url = f"https://api.census.gov/data/{ACS_YEAR}/{ACS_DATASET}"
    get_vars = ",".join(["NAME"] + variables)

    params = {
        "get": get_vars,
        "for": "block group:*",
        "in": f"state:{STATE_FIPS} county:{COBB_COUNTY_FIPS}",
    }

    response = requests.get(url, params=params, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed ACS fetch for {group}. "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

    data = response.json()
    df = pd.DataFrame(data[1:], columns=data[0])

    df["GEOID"] = make_block_group_geoid(df)
    df["county_fips"] = COBB_COUNTY_FIPS
    df["state_fips"] = STATE_FIPS

    return df


def _to_numeric_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """
    Convert selected columns to numeric values.
    """
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _build_step5_predictors() -> pd.DataFrame:
    """
    Build first-pass ACS predictors for Cobb block groups.
    """
    b25009_vars = [f"B25009_{i:03d}E" for i in range(1, 18)]
    b19001_vars = [f"B19001_{i:03d}E" for i in range(1, 18)]

    df_size = _fetch_acs_table_for_cobb("B25009", b25009_vars)
    df_income = _fetch_acs_table_for_cobb("B19001", b19001_vars)

    df_size = _to_numeric_cols(df_size, b25009_vars)
    df_income = _to_numeric_cols(df_income, b19001_vars)

    df = df_size.merge(
        df_income[["GEOID"] + b19001_vars],
        on="GEOID",
        how="left",
    )

    df["total_households"] = df["B25009_001E"]

    df["hh_size_1"] = df["B25009_003E"] + df["B25009_011E"]
    df["hh_size_2"] = df["B25009_004E"] + df["B25009_012E"]
    df["hh_size_3"] = df["B25009_005E"] + df["B25009_013E"]
    df["hh_size_4"] = df["B25009_006E"] + df["B25009_014E"]
    df["hh_size_5"] = df["B25009_007E"] + df["B25009_015E"]
    df["hh_size_6plus"] = (
        df["B25009_008E"]
        + df["B25009_009E"]
        + df["B25009_016E"]
        + df["B25009_017E"]
    )

    df["hh_income_lt_25k"] = (
        df["B19001_002E"]
        + df["B19001_003E"]
        + df["B19001_004E"]
        + df["B19001_005E"]
    )
    df["hh_income_25k_50k"] = (
        df["B19001_006E"]
        + df["B19001_007E"]
        + df["B19001_008E"]
        + df["B19001_009E"]
        + df["B19001_010E"]
    )
    df["hh_income_50k_100k"] = (
        df["B19001_011E"]
        + df["B19001_012E"]
        + df["B19001_013E"]
    )
    df["hh_income_100k_plus"] = (
        df["B19001_014E"]
        + df["B19001_015E"]
        + df["B19001_016E"]
        + df["B19001_017E"]
    )

    keep_cols = [
        "GEOID",
        "state",
        "county",
        "tract",
        "block group",
        "NAME",
        "total_households",
        "hh_size_1",
        "hh_size_2",
        "hh_size_3",
        "hh_size_4",
        "hh_size_5",
        "hh_size_6plus",
        "hh_income_lt_25k",
        "hh_income_25k_50k",
        "hh_income_50k_100k",
        "hh_income_100k_plus",
    ]

    df = df[keep_cols].copy()
    df["county"] = df["county"].astype(str).str.zfill(3)
    df = df[df["county"] == COBB_COUNTY_FIPS].copy()
    df = df.sort_values("GEOID").drop_duplicates(subset=["GEOID"]).reset_index(drop=True)

    df_cobb_bg = _load_cobb_block_groups_for_step4()[
        ["GEOID", "state", "county", "tract", "block group", "county_name"]
    ]

    df = df_cobb_bg.merge(
        df,
        on=["GEOID", "state", "county", "tract", "block group"],
        how="left",
    )

    predictor_cols = [
        "total_households",
        "hh_size_1",
        "hh_size_2",
        "hh_size_3",
        "hh_size_4",
        "hh_size_5",
        "hh_size_6plus",
        "hh_income_lt_25k",
        "hh_income_25k_50k",
        "hh_income_50k_100k",
        "hh_income_100k_plus",
    ]

    for col in predictor_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round(0).astype(int)

    if "NAME" in df.columns:
        df["NAME"] = df["NAME"].fillna("")

    return df


def _step5_qa_lines(df: pd.DataFrame) -> list[str]:
    """
    Build a text QA report for Step 5.
    """
    lines = []
    lines.append("Step 5 QA Report - Cobb ACS Predictors")
    lines.append("=" * 80)
    lines.append(f"Rows: {len(df):,}")
    lines.append("")

    bad_geoid_len = df[df["GEOID"].astype(str).str.len() != 12]
    bad_geoid_prefix = df[~df["GEOID"].astype(str).str.startswith("13067")]
    dup_geoid = df[df["GEOID"].duplicated(keep=False)]

    lines.append("GEOID checks:")
    lines.append(
        "PASS: GEOID length is 12 for all rows."
        if bad_geoid_len.empty else f"FAIL: {len(bad_geoid_len):,} rows with bad GEOID length."
    )
    lines.append(
        "PASS: All GEOIDs start with 13067."
        if bad_geoid_prefix.empty else f"FAIL: {len(bad_geoid_prefix):,} rows not in Cobb prefix."
    )
    lines.append(
        "PASS: No duplicate GEOIDs."
        if dup_geoid.empty else f"FAIL: {len(dup_geoid):,} duplicate GEOID rows found."
    )
    lines.append("")

    size_sum = (
        df["hh_size_1"]
        + df["hh_size_2"]
        + df["hh_size_3"]
        + df["hh_size_4"]
        + df["hh_size_5"]
        + df["hh_size_6plus"]
    )
    income_sum = (
        df["hh_income_lt_25k"]
        + df["hh_income_25k_50k"]
        + df["hh_income_50k_100k"]
        + df["hh_income_100k_plus"]
    )

    size_diff = (size_sum - df["total_households"]).abs()
    income_diff = (income_sum - df["total_households"]).abs()

    lines.append("Category sum checks against total_households:")
    lines.append(f"  Max |size_sum - total_households|: {int(size_diff.max()):,}")
    lines.append(f"  Max |income_sum - total_households|: {int(income_diff.max()):,}")
    lines.append(f"  Rows with size mismatch: {int((size_diff != 0).sum()):,}")
    lines.append(f"  Rows with income mismatch: {int((income_diff != 0).sum()):,}")
    lines.append("")

    predictor_cols = [
        "total_households",
        "hh_size_1",
        "hh_size_2",
        "hh_size_3",
        "hh_size_4",
        "hh_size_5",
        "hh_size_6plus",
        "hh_income_lt_25k",
        "hh_income_25k_50k",
        "hh_income_50k_100k",
        "hh_income_100k_plus",
    ]

    negative_count = int((df[predictor_cols] < 0).sum().sum())

    lines.append("Value checks:")
    lines.append(
        "PASS: No negative predictor values."
        if negative_count == 0 else f"FAIL: Found {negative_count:,} negative predictor values."
    )
    lines.append(f"Rows with total_households = 0: {int((df['total_households'] == 0).sum()):,}")

    return lines


# ---------------------------------------------------------------------
# Step 5 runner
# ---------------------------------------------------------------------

def run_step_5_cobb() -> None:
    """
    Step 5:
    Prepare ACS household predictors for Cobb County block groups.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    df = _build_step5_predictors()
    df.to_csv(STEP5_COBB_ACS_PREDICTORS_CSV, index=False)

    qa_lines = _step5_qa_lines(df)
    save_qa_report(qa_lines, STEP5_COBB_QA_TXT)

    print(f"Saved Step 5 ACS predictors: {STEP5_COBB_ACS_PREDICTORS_CSV}")
    print(f"Saved Step 5 QA report: {STEP5_COBB_QA_TXT}")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run regression data prep steps."
    )
    parser.add_argument(
        "--step1-cobb",
        action="store_true",
        help="Run Step 1 Cobb block-group geography fetch + QA.",
    )
    parser.add_argument(
        "--step4-cobb",
        action="store_true",
        help="Run Step 4 Cobb residential sqft aggregation + QA.",
    )
    parser.add_argument(
        "--step5-cobb",
        action="store_true",
        help="Run Step 5 Cobb ACS predictor prep + QA.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Default behavior: run Step 4 Cobb.
    if not args.step1_cobb and not args.step4_cobb and not args.step5_cobb:
        run_step_4_cobb()
    else:
        if args.step1_cobb:
            run_step_1_cobb()
        if args.step4_cobb:
            run_step_4_cobb()
        if args.step5_cobb:
            run_step_5_cobb()