#!/usr/bin/env python3

"""
run_regression.py

Regression workflow for block-group residential square footage modeling.

Implemented:
- Step 1: Define initial geography (Cobb block groups)
- Step 4: Aggregate residential square footage by block group
- Step 5: Prepare ACS household predictors
- Step 6: Join parcel-derived dependent variable to ACS predictors
"""

from pathlib import Path
import argparse
import numpy as np
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

# Step 6 outputs (Cobb modeling table)
STEP6_COBB_MODELING_TABLE_CSV = OUTPUT_DIR / "regression_modeling_table_cobb_bg.csv"
STEP6_COBB_QA_TXT = OUTPUT_DIR / "qa_step6_modeling_table_cobb_2024.txt"

# Step 7 outputs (Cobb regressions)
STEP7_COBB_RESULTS_TXT = OUTPUT_DIR / "regression_results_cobb.txt"
STEP7_COBB_DIAGNOSTICS_CSV = OUTPUT_DIR / "regression_diagnostics_cobb.csv"

# Step 8 outputs (Cobb model specification comparison)
STEP8_COBB_MODEL_COMPARISON_CSV = OUTPUT_DIR / "regression_step8_model_comparison_cobb.csv"
STEP8_COBB_RESULTS_TXT = OUTPUT_DIR / "regression_step8_results_cobb.txt"
STEP8_COBB_DIAGNOSTICS_CSV = OUTPUT_DIR / "regression_step8_diagnostics_cobb.csv"

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
# Step 6 helpers
# ---------------------------------------------------------------------

def _load_step4_cobb_res_sqft() -> pd.DataFrame:
    """
    Load Step 4 Cobb residential square-footage table.
    If missing, run Step 4 first.
    """
    if not STEP4_COBB_BG_RES_SQFT_CSV.exists():
        print("Step 4 output not found. Running Step 4 automatically...")
        run_step_4_cobb()

    df = pd.read_csv(STEP4_COBB_BG_RES_SQFT_CSV, dtype={"GEOID": str})
    df["GEOID"] = _normalize_geoid(df["GEOID"])

    numeric_cols = [
        "residential_record_count",
        "total_res_sqft",
        "zero_res_sqft_record_count",
        "missing_res_sqft_record_count",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _load_step5_cobb_acs_predictors() -> pd.DataFrame:
    """
    Load Step 5 Cobb ACS predictor table.
    If missing, run Step 5 first.
    """
    if not STEP5_COBB_ACS_PREDICTORS_CSV.exists():
        print("Step 5 output not found. Running Step 5 automatically...")
        run_step_5_cobb()

    df = pd.read_csv(STEP5_COBB_ACS_PREDICTORS_CSV, dtype={"GEOID": str})
    df["GEOID"] = _normalize_geoid(df["GEOID"])

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
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _build_step6_modeling_table() -> pd.DataFrame:
    """
    Join Step 4 parcel-derived dependent variable to Step 5 ACS predictors.

    Output should have one row per Cobb block group.
    """
    df_sqft = _load_step4_cobb_res_sqft()
    df_acs = _load_step5_cobb_acs_predictors()

    if df_sqft["GEOID"].duplicated().any():
        duplicated = df_sqft.loc[df_sqft["GEOID"].duplicated(keep=False), "GEOID"].tolist()
        raise ValueError(f"Step 4 table has duplicate GEOIDs. First duplicates: {duplicated[:10]}")

    if df_acs["GEOID"].duplicated().any():
        duplicated = df_acs.loc[df_acs["GEOID"].duplicated(keep=False), "GEOID"].tolist()
        raise ValueError(f"Step 5 table has duplicate GEOIDs. First duplicates: {duplicated[:10]}")

    sqft_cols = [
        "GEOID",
        "total_res_sqft",
        "residential_record_count",
        "zero_res_sqft_record_count",
        "missing_res_sqft_record_count",
    ]
    sqft_cols = [c for c in sqft_cols if c in df_sqft.columns]

    acs_cols = [
        "GEOID",
        "state",
        "county",
        "county_name",
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
    acs_cols = [c for c in acs_cols if c in df_acs.columns]

    out = df_acs[acs_cols].merge(
        df_sqft[sqft_cols],
        on="GEOID",
        how="left",
        indicator=True,
    )

    out["parcel_join_status"] = out["_merge"].map(
        {
            "both": "matched",
            "left_only": "missing_parcel_sqft",
            "right_only": "unexpected_right_only",
        }
    )
    out = out.drop(columns=["_merge"])

    parcel_numeric_cols = [
        "total_res_sqft",
        "residential_record_count",
        "zero_res_sqft_record_count",
        "missing_res_sqft_record_count",
    ]
    for col in parcel_numeric_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).round(0).astype("int64")

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
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    if "county" in out.columns:
        out["county"] = out["county"].astype(str).str.zfill(3)

    out = out.sort_values("GEOID").reset_index(drop=True)

    preferred_order = [
        "GEOID",
        "state",
        "county",
        "county_name",
        "tract",
        "block group",
        "NAME",
        "total_res_sqft",
        "residential_record_count",
        "zero_res_sqft_record_count",
        "missing_res_sqft_record_count",
        "parcel_join_status",
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
    ordered_cols = [c for c in preferred_order if c in out.columns]
    remaining_cols = [c for c in out.columns if c not in ordered_cols]

    return out[ordered_cols + remaining_cols]


def _step6_qa_lines(df_model: pd.DataFrame, df_sqft: pd.DataFrame, df_acs: pd.DataFrame) -> list[str]:
    """
    Build a text QA report for Step 6.
    """
    lines = []
    lines.append("Step 6 QA Report - Cobb Modeling Table")
    lines.append("=" * 80)
    lines.append(f"Step 4 parcel/BG rows: {len(df_sqft):,}")
    lines.append(f"Step 5 ACS predictor rows: {len(df_acs):,}")
    lines.append(f"Modeling table rows: {len(df_model):,}")
    lines.append("")

    lines.append("GEOID checks:")
    bad_geoid_len = df_model[df_model["GEOID"].astype(str).str.len() != 12]
    bad_geoid_prefix = df_model[~df_model["GEOID"].astype(str).str.startswith("13067")]
    duplicated_geoids = df_model[df_model["GEOID"].duplicated(keep=False)]

    lines.append(
        "PASS: All modeling-table GEOIDs are 12 characters."
        if bad_geoid_len.empty else f"FAIL: {len(bad_geoid_len):,} rows have bad GEOID length."
    )
    lines.append(
        "PASS: All modeling-table GEOIDs start with 13067."
        if bad_geoid_prefix.empty else f"FAIL: {len(bad_geoid_prefix):,} rows do not start with 13067."
    )
    lines.append(
        "PASS: Modeling table has one row per GEOID."
        if duplicated_geoids.empty else f"FAIL: {len(duplicated_geoids):,} duplicate GEOID rows found."
    )
    lines.append("")

    lines.append("Join checks:")
    if "parcel_join_status" in df_model.columns:
        status_counts = df_model["parcel_join_status"].value_counts(dropna=False).sort_index()
        for status, count in status_counts.items():
            lines.append(f"  {status}: {count:,}")
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

    parcel_cols = [
        "total_res_sqft",
        "residential_record_count",
        "zero_res_sqft_record_count",
        "missing_res_sqft_record_count",
    ]

    lines.append("Missing-value checks:")
    for col in parcel_cols + predictor_cols:
        if col in df_model.columns:
            missing_count = int(df_model[col].isna().sum())
            lines.append(f"  {col}: {missing_count:,} missing")
    lines.append("")

    if "total_households" in df_model.columns:
        zero_hh = int((df_model["total_households"] == 0).sum())
        lines.append(f"Rows with total_households = 0: {zero_hh:,}")

    if "total_res_sqft" in df_model.columns:
        zero_sqft = int((df_model["total_res_sqft"] == 0).sum())
        total_sqft = int(df_model["total_res_sqft"].sum())
        lines.append(f"Rows with total_res_sqft = 0: {zero_sqft:,}")
        lines.append(f"Total residential sqft in modeling table: {total_sqft:,}")

    lines.append("")

    if {"total_res_sqft", "total_households"}.issubset(df_model.columns):
        valid_ratio = df_model["total_households"] > 0
        sqft_per_hh = df_model.loc[valid_ratio, "total_res_sqft"] / df_model.loc[valid_ratio, "total_households"]
        lines.append("Sqft per household sanity summary, excluding zero-household BGs:")
        lines.append(f"  Count: {len(sqft_per_hh):,}")
        lines.append(f"  Min: {sqft_per_hh.min():,.2f}")
        lines.append(f"  Median: {sqft_per_hh.median():,.2f}")
        lines.append(f"  Mean: {sqft_per_hh.mean():,.2f}")
        lines.append(f"  Max: {sqft_per_hh.max():,.2f}")
        lines.append("")

    if {"GEOID", "total_res_sqft", "total_households"}.issubset(df_model.columns):
        top10 = df_model.nlargest(10, "total_res_sqft")[["GEOID", "total_res_sqft", "total_households"]]
        lines.append("Top 10 block groups by total_res_sqft:")
        for _, row in top10.iterrows():
            lines.append(
                f"  {row['GEOID']}: total_res_sqft={int(row['total_res_sqft']):,}, "
                f"total_households={int(row['total_households']):,}"
            )

    return lines


# ---------------------------------------------------------------------
# Step 6 runner
# ---------------------------------------------------------------------

def run_step_6_cobb() -> None:
    """
    Step 6:
    Join parcel-derived dependent variable to ACS predictors for Cobb County.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    df_sqft = _load_step4_cobb_res_sqft()
    df_acs = _load_step5_cobb_acs_predictors()
    df_model = _build_step6_modeling_table()

    df_model.to_csv(STEP6_COBB_MODELING_TABLE_CSV, index=False)

    qa_lines = _step6_qa_lines(df_model, df_sqft, df_acs)
    save_qa_report(qa_lines, STEP6_COBB_QA_TXT)

    print(f"Saved Step 6 modeling table: {STEP6_COBB_MODELING_TABLE_CSV}")
    print(f"Saved Step 6 QA report: {STEP6_COBB_QA_TXT}")


# ---------------------------------------------------------------------
# Step 7 helpers
# ---------------------------------------------------------------------

def _load_step6_cobb_modeling_table() -> pd.DataFrame:
    """
    Load Step 6 Cobb modeling table.
    If missing, run Step 6 first.
    """
    if not STEP6_COBB_MODELING_TABLE_CSV.exists():
        print("Step 6 output not found. Running Step 6 automatically...")
        run_step_6_cobb()

    df = pd.read_csv(STEP6_COBB_MODELING_TABLE_CSV, dtype={"GEOID": str})
    df["GEOID"] = _normalize_geoid(df["GEOID"])

    numeric_cols = [
        "total_res_sqft",
        "residential_record_count",
        "zero_res_sqft_record_count",
        "missing_res_sqft_record_count",
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

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _fit_ols(
    df: pd.DataFrame,
    y_col: str,
    x_cols: list[str],
    model_name: str,
    include_intercept: bool = True,
) -> dict:
    """
    Fit OLS with numpy and return summary statistics plus predictions.

    This intentionally avoids adding a statsmodels dependency for the first
    sanity-check pass.
    """
    needed_cols = [y_col] + x_cols
    model_df = df.dropna(subset=needed_cols).copy()

    y = model_df[y_col].to_numpy(dtype=float)
    x = model_df[x_cols].to_numpy(dtype=float)

    if include_intercept:
        x_design = np.column_stack([np.ones(len(model_df)), x])
        coefficient_names = ["intercept"] + x_cols
    else:
        x_design = x
        coefficient_names = x_cols

    coefficients, residual_sum_squares_raw, rank, singular_values = np.linalg.lstsq(
        x_design,
        y,
        rcond=None,
    )

    predicted = x_design @ coefficients
    residual = y - predicted

    n_obs = len(y)
    n_params = x_design.shape[1]

    sse = float(np.sum(residual ** 2))
    tss = float(np.sum((y - y.mean()) ** 2))
    r_squared = 1 - (sse / tss) if tss != 0 else np.nan

    if n_obs > n_params and tss != 0:
        adj_r_squared = 1 - ((sse / (n_obs - n_params)) / (tss / (n_obs - 1)))
    else:
        adj_r_squared = np.nan

    rmse = float(np.sqrt(sse / n_obs)) if n_obs > 0 else np.nan
    mae = float(np.mean(np.abs(residual))) if n_obs > 0 else np.nan

    if n_obs > n_params:
        sigma2 = sse / (n_obs - n_params)
        xtx_inv = np.linalg.pinv(x_design.T @ x_design)
        standard_errors = np.sqrt(np.diag(sigma2 * xtx_inv))
    else:
        standard_errors = np.full(len(coefficients), np.nan)

    coef_df = pd.DataFrame(
        {
            "term": coefficient_names,
            "coefficient": coefficients,
            "std_error": standard_errors,
        }
    )

    prediction_df = model_df[["GEOID", y_col]].copy()
    prediction_df["predicted_res_sqft"] = predicted
    prediction_df["residual"] = residual
    prediction_df["abs_residual"] = np.abs(residual)
    prediction_df["abs_pct_error"] = np.where(
        prediction_df[y_col] != 0,
        prediction_df["abs_residual"] / prediction_df[y_col],
        np.nan,
    )

    return {
        "model_name": model_name,
        "include_intercept": include_intercept,
        "y_col": y_col,
        "x_cols": x_cols,
        "n_obs": n_obs,
        "n_params": n_params,
        "rank": int(rank),
        "r_squared": r_squared,
        "adj_r_squared": adj_r_squared,
        "rmse": rmse,
        "mae": mae,
        "coefficients": coef_df,
        "predictions": prediction_df,
    }


def _format_ols_summary(result: dict) -> list[str]:
    """
    Format one OLS result as text report lines.
    """
    lines = []

    lines.append(result["model_name"])
    lines.append("-" * 80)
    lines.append(f"Dependent variable: {result['y_col']}")
    lines.append(f"Predictors: {', '.join(result['x_cols'])}")
    lines.append(f"Includes intercept: {result['include_intercept']}")
    lines.append(f"Observations: {result['n_obs']:,}")
    lines.append(f"Parameters: {result['n_params']:,}")
    lines.append(f"Design matrix rank: {result['rank']:,}")
    lines.append(f"R-squared: {result['r_squared']:.6f}")
    lines.append(f"Adjusted R-squared: {result['adj_r_squared']:.6f}")
    lines.append(f"RMSE: {result['rmse']:,.2f}")
    lines.append(f"MAE: {result['mae']:,.2f}")
    lines.append("")
    lines.append("Coefficients:")
    lines.append(f"{'term':<28} {'coefficient':>18} {'std_error':>18}")

    for _, row in result["coefficients"].iterrows():
        lines.append(
            f"{row['term']:<28} "
            f"{row['coefficient']:>18,.6f} "
            f"{row['std_error']:>18,.6f}"
        )

    lines.append("")

    return lines


def _build_step7_diagnostics(
    df_model: pd.DataFrame,
    combined_result: dict,
) -> pd.DataFrame:
    """
    Build block-group diagnostics from the combined first-pass model.
    """
    diag = combined_result["predictions"].copy()

    keep_cols = [
        "GEOID",
        "county_name",
        "NAME",
        "total_households",
        "residential_record_count",
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
    keep_cols = [c for c in keep_cols if c in df_model.columns]

    diag = diag.merge(
        df_model[keep_cols],
        on="GEOID",
        how="left",
    )

    diag = diag.rename(columns={"total_res_sqft": "observed_res_sqft"})

    ordered_cols = [
        "GEOID",
        "county_name",
        "NAME",
        "observed_res_sqft",
        "predicted_res_sqft",
        "residual",
        "abs_residual",
        "abs_pct_error",
        "total_households",
        "residential_record_count",
    ]
    ordered_cols = [c for c in ordered_cols if c in diag.columns]
    remaining_cols = [c for c in diag.columns if c not in ordered_cols]

    return diag[ordered_cols + remaining_cols].sort_values(
        "abs_residual",
        ascending=False,
    ).reset_index(drop=True)


def _step7_report_lines(results: list[dict], diagnostics: pd.DataFrame) -> list[str]:
    """
    Build Step 7 regression results report.
    """
    lines = []

    lines.append("Step 7 Regression Results - Cobb Initial Sanity-Check Models")
    lines.append("=" * 80)
    lines.append(f"ACS year: {ACS_YEAR}")
    lines.append(f"Diagnostics model: Combined first-pass model")
    lines.append("")

    for result in results:
        lines.extend(_format_ols_summary(result))

    lines.append("Largest absolute residuals from combined first-pass model:")
    lines.append("-" * 80)

    top = diagnostics.head(15)
    for _, row in top.iterrows():
        abs_pct_error = row["abs_pct_error"]
        abs_pct_error_text = "NA" if pd.isna(abs_pct_error) else f"{abs_pct_error:.3f}"

        lines.append(
            f"{row['GEOID']}: "
            f"observed={row['observed_res_sqft']:,.0f}, "
            f"predicted={row['predicted_res_sqft']:,.0f}, "
            f"residual={row['residual']:,.0f}, "
            f"abs_pct_error={abs_pct_error_text}"
        )

    lines.append("")

    return lines


# ---------------------------------------------------------------------
# Step 7 runner
# ---------------------------------------------------------------------

def run_step_7_cobb() -> None:
    """
    Step 7:
    Run initial Cobb sanity-check OLS regressions.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    df_model = _load_step6_cobb_modeling_table()

    # For the first pass, exclude rows with zero households because the ACS
    # household predictors cannot explain residential square footage there.
    df_reg = df_model[df_model["total_households"] > 0].copy()

    y_col = "total_res_sqft"

    size_cols = [
        "hh_size_1",
        "hh_size_2",
        "hh_size_3",
        "hh_size_4",
        "hh_size_5",
        "hh_size_6plus",
    ]

    income_cols = [
        "hh_income_lt_25k",
        "hh_income_25k_50k",
        "hh_income_50k_100k",
        "hh_income_100k_plus",
    ]

    model_1 = _fit_ols(
        df=df_reg,
        y_col=y_col,
        x_cols=["total_households"],
        model_name="Model 1: Total Households Only",
        include_intercept=True,
    )

    model_2 = _fit_ols(
        df=df_reg,
        y_col=y_col,
        x_cols=size_cols,
        model_name="Model 2: Household Size Counts, No Intercept",
        include_intercept=False,
    )

    model_3 = _fit_ols(
        df=df_reg,
        y_col=y_col,
        x_cols=income_cols,
        model_name="Model 3: Income Category Counts, No Intercept",
        include_intercept=False,
    )

    model_4 = _fit_ols(
        df=df_reg,
        y_col=y_col,
        x_cols=size_cols + income_cols,
        model_name="Model 4: Combined First-Pass Model, No Intercept",
        include_intercept=False,
    )

    results = [model_1, model_2, model_3, model_4]

    diagnostics = _build_step7_diagnostics(df_model, model_4)
    diagnostics.to_csv(STEP7_COBB_DIAGNOSTICS_CSV, index=False)

    report_lines = _step7_report_lines(results, diagnostics)
    save_qa_report(report_lines, STEP7_COBB_RESULTS_TXT)

    print(f"Saved Step 7 regression results: {STEP7_COBB_RESULTS_TXT}")
    print(f"Saved Step 7 diagnostics: {STEP7_COBB_DIAGNOSTICS_CSV}")


# ---------------------------------------------------------------------
# Step 8 helpers
# ---------------------------------------------------------------------

def _prepare_step8_modeling_data(df_model: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare share and intensity variables for Step 8 specification testing.
    """
    df = df_model.copy()

    df = df[df["total_households"] > 0].copy()

    df["sqft_per_household"] = df["total_res_sqft"] / df["total_households"]

    size_cols = [
        "hh_size_1",
        "hh_size_2",
        "hh_size_3",
        "hh_size_4",
        "hh_size_5",
        "hh_size_6plus",
    ]

    income_cols = [
        "hh_income_lt_25k",
        "hh_income_25k_50k",
        "hh_income_50k_100k",
        "hh_income_100k_plus",
    ]

    for col in size_cols:
        share_col = col.replace("hh_size_", "share_size_")
        df[share_col] = df[col] / df["total_households"]

    income_share_names = {
        "hh_income_lt_25k": "share_income_lt_25k",
        "hh_income_25k_50k": "share_income_25k_50k",
        "hh_income_50k_100k": "share_income_50k_100k",
        "hh_income_100k_plus": "share_income_100k_plus",
    }

    for col, share_col in income_share_names.items():
        df[share_col] = df[col] / df["total_households"]

    return df


def _mean_absolute_percent_error(prediction_df: pd.DataFrame, y_col: str) -> float:
    """
    Compute MAPE excluding rows where observed y is zero.
    """
    valid = prediction_df[y_col] != 0
    if valid.sum() == 0:
        return np.nan

    return float(
        np.mean(
            np.abs(
                prediction_df.loc[valid, "residual"]
                / prediction_df.loc[valid, y_col]
            )
        )
    )


def _step8_model_comparison_rows(results: list[dict]) -> pd.DataFrame:
    """
    Build model comparison table for Step 8.
    """
    rows = []

    for result in results:
        mape = _mean_absolute_percent_error(
            result["predictions"],
            result["y_col"],
        )

        rows.append(
            {
                "model_name": result["model_name"],
                "dependent_variable": result["y_col"],
                "include_intercept": result["include_intercept"],
                "n_obs": result["n_obs"],
                "n_params": result["n_params"],
                "rank": result["rank"],
                "r_squared": result["r_squared"],
                "adj_r_squared": result["adj_r_squared"],
                "rmse": result["rmse"],
                "mae": result["mae"],
                "mape": mape,
                "predictors": ", ".join(result["x_cols"]),
            }
        )

    return pd.DataFrame(rows)


def _build_step8_diagnostics(
    df_model: pd.DataFrame,
    result: dict,
    diagnostic_model_label: str,
) -> pd.DataFrame:
    """
    Build Step 8 diagnostics for one chosen model.

    If the chosen model predicts sqft_per_household, also convert predictions
    back to total residential square feet for residual review.
    """
    pred = result["predictions"].copy()

    keep_cols = [
        "GEOID",
        "county_name",
        "NAME",
        "total_res_sqft",
        "total_households",
        "residential_record_count",
        "sqft_per_household",
        "share_size_1",
        "share_size_2",
        "share_size_3",
        "share_size_4",
        "share_size_5",
        "share_size_6plus",
        "share_income_lt_25k",
        "share_income_25k_50k",
        "share_income_50k_100k",
        "share_income_100k_plus",
    ]
    keep_cols = [c for c in keep_cols if c in df_model.columns]

    diag = pred.merge(
        df_model[keep_cols],
        on="GEOID",
        how="left",
        suffixes=("", "_model_table"),
    )

    diag["diagnostic_model"] = diagnostic_model_label

    if result["y_col"] == "sqft_per_household":
        diag = diag.rename(
            columns={
                "sqft_per_household": "observed_sqft_per_household",
                "predicted_res_sqft": "predicted_sqft_per_household",
            }
        )
        diag["predicted_total_res_sqft"] = (
            diag["predicted_sqft_per_household"] * diag["total_households"]
        )
        diag["total_res_sqft_residual"] = (
            diag["total_res_sqft"] - diag["predicted_total_res_sqft"]
        )
        diag["total_res_sqft_abs_residual"] = diag["total_res_sqft_residual"].abs()
        diag["total_res_sqft_abs_pct_error"] = np.where(
            diag["total_res_sqft"] != 0,
            diag["total_res_sqft_abs_residual"] / diag["total_res_sqft"],
            np.nan,
        )

        sort_col = "total_res_sqft_abs_residual"
    else:
        diag = diag.rename(
            columns={
                "total_res_sqft": "observed_res_sqft",
                "predicted_res_sqft": "predicted_total_res_sqft",
            }
        )
        sort_col = "abs_residual"

    return diag.sort_values(sort_col, ascending=False).reset_index(drop=True)


def _step8_report_lines(
    results: list[dict],
    comparison_df: pd.DataFrame,
    diagnostics: pd.DataFrame,
    diagnostic_model_name: str,
) -> list[str]:
    """
    Build Step 8 text report.
    """
    lines = []

    lines.append("Step 8 Model Specification Comparison - Cobb")
    lines.append("=" * 80)
    lines.append(f"ACS year: {ACS_YEAR}")
    lines.append(f"Diagnostic model: {diagnostic_model_name}")
    lines.append("")

    lines.append("Model comparison:")
    lines.append("-" * 80)
    lines.append(
        f"{'model_name':<48} "
        f"{'dep_var':<22} "
        f"{'adj_r2':>10} "
        f"{'rmse':>14} "
        f"{'mae':>14} "
        f"{'mape':>10} "
        f"{'rank':>6} "
        f"{'params':>6}"
    )

    for _, row in comparison_df.iterrows():
        lines.append(
            f"{row['model_name']:<48} "
            f"{row['dependent_variable']:<22} "
            f"{row['adj_r_squared']:>10.6f} "
            f"{row['rmse']:>14,.2f} "
            f"{row['mae']:>14,.2f} "
            f"{row['mape']:>10.4f} "
            f"{int(row['rank']):>6} "
            f"{int(row['n_params']):>6}"
        )

    lines.append("")
    lines.append("Detailed model summaries:")
    lines.append("=" * 80)
    lines.append("")

    for result in results:
        lines.extend(_format_ols_summary(result))

    lines.append("")
    lines.append(f"Largest total-square-foot residuals from {diagnostic_model_name}:")
    lines.append("-" * 80)

    top = diagnostics.head(15)
    for _, row in top.iterrows():
        if "observed_res_sqft" in row:
            observed = row["observed_res_sqft"]
        else:
            observed = row["total_res_sqft"]

        predicted = row["predicted_total_res_sqft"]

        if "total_res_sqft_residual" in row:
            residual = row["total_res_sqft_residual"]
            abs_pct_error = row["total_res_sqft_abs_pct_error"]
        else:
            residual = row["residual"]
            abs_pct_error = row["abs_pct_error"]

        abs_pct_error_text = "NA" if pd.isna(abs_pct_error) else f"{abs_pct_error:.3f}"

        lines.append(
            f"{row['GEOID']}: "
            f"observed={observed:,.0f}, "
            f"predicted={predicted:,.0f}, "
            f"residual={residual:,.0f}, "
            f"abs_pct_error={abs_pct_error_text}"
        )

    lines.append("")
    lines.append("Initial interpretation notes:")
    lines.append("-" * 80)
    lines.append(
        "Share-based models avoid the rank-deficiency problem caused by including "
        "both complete household-size counts and complete income-count categories."
    )
    lines.append(
        "Sqft-per-household models explain intensity rather than total scale; "
        "their RMSE/MAE are in square feet per household, not total block-group square feet."
    )
    lines.append(
        "For converting household forecasts to square-footage demand, prefer a model "
        "with stable coefficients and clear total-square-foot prediction behavior."
    )

    return lines


# ---------------------------------------------------------------------
# Step 8 runner
# ---------------------------------------------------------------------

def run_step_8_cobb() -> None:
    """
    Step 8:
    Compare candidate main modeling specifications for Cobb County.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    df_model = _load_step6_cobb_modeling_table()
    df_reg = _prepare_step8_modeling_data(df_model)

    income_count_cols = [
        "hh_income_lt_25k",
        "hh_income_25k_50k",
        "hh_income_50k_100k",
        "hh_income_100k_plus",
    ]

    income_share_cols_reference_100k = [
        "share_income_lt_25k",
        "share_income_25k_50k",
        "share_income_50k_100k",
    ]

    size_share_cols_reference_6plus = [
        "share_size_1",
        "share_size_2",
        "share_size_3",
        "share_size_4",
        "share_size_5",
    ]

    model_a = _fit_ols(
        df=df_reg,
        y_col="total_res_sqft",
        x_cols=income_count_cols,
        model_name="A: Income Counts, No Intercept",
        include_intercept=False,
    )

    model_b = _fit_ols(
        df=df_reg,
        y_col="total_res_sqft",
        x_cols=["total_households"] + income_share_cols_reference_100k,
        model_name="B: Total HH + Income Shares",
        include_intercept=True,
    )

    model_c = _fit_ols(
        df=df_reg,
        y_col="total_res_sqft",
        x_cols=["total_households"] + size_share_cols_reference_6plus + income_share_cols_reference_100k,
        model_name="C: Total HH + Size Shares + Income Shares",
        include_intercept=True,
    )

    model_d = _fit_ols(
        df=df_reg,
        y_col="sqft_per_household",
        x_cols=income_share_cols_reference_100k,
        model_name="D: SqFt per HH + Income Shares",
        include_intercept=True,
    )

    model_e = _fit_ols(
        df=df_reg,
        y_col="sqft_per_household",
        x_cols=size_share_cols_reference_6plus + income_share_cols_reference_100k,
        model_name="E: SqFt per HH + Size Shares + Income Shares",
        include_intercept=True,
    )

    results = [model_a, model_b, model_c, model_d, model_e]

    comparison_df = _step8_model_comparison_rows(results)
    comparison_df.to_csv(STEP8_COBB_MODEL_COMPARISON_CSV, index=False)

    # Use Model C for diagnostics because it is the richest total-square-foot
    # model that avoids complete category-sum redundancy.
    diagnostic_model = model_c
    diagnostic_model_name = diagnostic_model["model_name"]

    diagnostics = _build_step8_diagnostics(
        df_model=df_reg,
        result=diagnostic_model,
        diagnostic_model_label=diagnostic_model_name,
    )
    diagnostics.to_csv(STEP8_COBB_DIAGNOSTICS_CSV, index=False)

    report_lines = _step8_report_lines(
        results=results,
        comparison_df=comparison_df,
        diagnostics=diagnostics,
        diagnostic_model_name=diagnostic_model_name,
    )
    save_qa_report(report_lines, STEP8_COBB_RESULTS_TXT)

    print(f"Saved Step 8 model comparison: {STEP8_COBB_MODEL_COMPARISON_CSV}")
    print(f"Saved Step 8 regression results: {STEP8_COBB_RESULTS_TXT}")
    print(f"Saved Step 8 diagnostics: {STEP8_COBB_DIAGNOSTICS_CSV}")


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
    parser.add_argument(
        "--step6-cobb",
        action="store_true",
        help="Run Step 6 Cobb modeling-table join + QA.",
    )
    parser.add_argument(
        "--step7-cobb",
        action="store_true",
        help="Run Step 7 Cobb initial sanity-check regressions.",
    )
    parser.add_argument(
        "--step8-cobb",
        action="store_true",
        help="Run Step 8 Cobb model specification comparison.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Default behavior: run Step 8 Cobb, auto-running earlier outputs if needed.
    if (
        not args.step1_cobb
        and not args.step4_cobb
        and not args.step5_cobb
        and not args.step6_cobb
        and not args.step7_cobb
        and not args.step8_cobb
    ):
        run_step_8_cobb()
    else:
        if args.step1_cobb:
            run_step_1_cobb()
        if args.step4_cobb:
            run_step_4_cobb()
        if args.step5_cobb:
            run_step_5_cobb()
        if args.step6_cobb:
            run_step_6_cobb()
        if args.step7_cobb:
            run_step_7_cobb()
        if args.step8_cobb:
            run_step_8_cobb()