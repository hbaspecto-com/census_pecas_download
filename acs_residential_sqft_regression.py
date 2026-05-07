#!/usr/bin/env python3

"""
acs_residential_sqft_regression.py

Estimate expected residential square feet per occupied household using ACS
demographic and housing characteristics at the Census Block Group level for
Cobb County.

Regression specification:
    log(total_res_sqft_bg / occupied_households_bg)
    ~
    E_log_income_bg
    + E_log_hhsize_bg
    + share_households_with_children_bg
    + share_single_attached_bg
    + share_2_to_4_units_bg
    + share_5_to_19_units_bg
    + share_20plus_units_bg
    + share_mobile_other_bg
    + expected_bedrooms_bg

Weighted by occupied_households_bg (B25003_001E).
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

COUNTIES = {
    "067": "Cobb",
}

OUTPUT_DIR = Path("outputs")

# Input: parcel sqft aggregated to block groups
ARC_BG_RES_SQFT_CSV = OUTPUT_DIR / "arc_bg_res_sqft_2024.csv"

# Outputs
ACS_PREDICTORS_CSV = OUTPUT_DIR / "acs_sqft_predictors_cobb_2024.csv"
ACS_PREDICTORS_QA_TXT = OUTPUT_DIR / "qa_acs_sqft_predictors_cobb_2024.txt"
MODELING_TABLE_CSV = OUTPUT_DIR / "acs_sqft_modeling_table_cobb_2024.csv"
MODELING_TABLE_QA_TXT = OUTPUT_DIR / "qa_acs_sqft_modeling_table_cobb_2024.txt"
REGRESSION_RESULTS_TXT = OUTPUT_DIR / "acs_sqft_regression_results_cobb_2024.txt"
REGRESSION_DIAGNOSTICS_CSV = OUTPUT_DIR / "acs_sqft_regression_diagnostics_cobb_2024.csv"

# Dependent variable column name
Y_COL = "log_res_sqft_per_hh"

# Predictor column names (matches specification)
PREDICTOR_COLS = [
    "E_log_income_bg",
    "E_log_hhsize_bg",
    "share_households_with_children_bg",
    "share_single_attached_bg",
    "share_2_to_4_units_bg",
    "share_5_to_19_units_bg",
    "share_20plus_units_bg",
    "share_mobile_other_bg",
    "expected_bedrooms_bg",
]

# B19001 income bins: (variable_suffix, low, high)
# For the open-ended top bin (200k+), use 300_000 as representative value.
B19001_BINS = [
    ("002E",      0,    10_000),
    ("003E",  10_000,   15_000),
    ("004E",  15_000,   20_000),
    ("005E",  20_000,   25_000),
    ("006E",  25_000,   30_000),
    ("007E",  30_000,   35_000),
    ("008E",  35_000,   40_000),
    ("009E",  40_000,   45_000),
    ("010E",  45_000,   50_000),
    ("011E",  50_000,   60_000),
    ("012E",  60_000,   75_000),
    ("013E",  75_000,  100_000),
    ("014E", 100_000,  125_000),
    ("015E", 125_000,  150_000),
    ("016E", 150_000,  200_000),
    ("017E", 200_000,  300_000),  # open-ended top bin
]

# B11016 household size bins: (variable_suffix, size_value)
# Family households: 003E=2, 004E=3, 005E=4, 006E=5, 007E=6, 008E=7+
# Nonfamily households: 010E=1, 011E=2, 012E=3, 013E=4, 014E=5, 015E=6, 016E=7+
# For open-ended 7+ bin, use 7.5 as representative value.
B11016_BINS = [
    # (variable_suffix, size_value)
    ("003E", 2),    # family, 2-person
    ("004E", 3),    # family, 3-person
    ("005E", 4),    # family, 4-person
    ("006E", 5),    # family, 5-person
    ("007E", 6),    # family, 6-person
    ("008E", 7.5),  # family, 7-or-more-person
    ("010E", 1),    # nonfamily, 1-person
    ("011E", 2),    # nonfamily, 2-person
    ("012E", 3),    # nonfamily, 3-person
    ("013E", 4),    # nonfamily, 4-person
    ("014E", 5),    # nonfamily, 5-person
    ("015E", 6),    # nonfamily, 6-person
    ("016E", 7.5),  # nonfamily, 7-or-more-person
]

# B25041 bedroom bins: (variable_suffix, bedroom_midpoint)
# 002E=no bedroom (0), 003E=1, 004E=2, 005E=3, 006E=4, 007E=5+
B25041_BINS = [
    ("002E", 0),    # no bedroom
    ("003E", 1),    # 1 bedroom
    ("004E", 2),    # 2 bedrooms
    ("005E", 3),    # 3 bedrooms
    ("006E", 4),    # 4 bedrooms
    ("007E", 5.5),  # 5 or more bedrooms
]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _make_geoid(df: pd.DataFrame) -> pd.Series:
    """
    Build 12-character block group GEOID from state/county/tract/block group columns.
    """
    return (
        df["state"].astype(str).str.zfill(2)
        + df["county"].astype(str).str.zfill(3)
        + df["tract"].astype(str).str.zfill(6)
        + df["block group"].astype(str).str.zfill(1)
    )


def _fetch_acs_table(
    group: str,
    variables: list[str],
    county_fips: str,
) -> pd.DataFrame:
    """
    Fetch one ACS table for a single county's block groups.
    """
    url = f"https://api.census.gov/data/{ACS_YEAR}/{ACS_DATASET}"
    get_vars = ",".join(["NAME"] + variables)

    params = {
        "get": get_vars,
        "for": "block group:*",
        "in": f"state:{STATE_FIPS} county:{county_fips}",
    }

    response = requests.get(url, params=params, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed ACS fetch for group={group}, county={county_fips}. "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

    data = response.json()
    df = pd.DataFrame(data[1:], columns=data[0])
    df["GEOID"] = _make_geoid(df)
    return df


def _fetch_acs_table_arc(group: str, variables: list[str]) -> pd.DataFrame:
    """
    Fetch one ACS table for all ARC counties and concatenate.
    """
    frames = []
    for county_fips, county_name in COUNTIES.items():
        print(f"  Fetching {group} for {county_name} County ({county_fips})...")
        df = _fetch_acs_table(group, variables, county_fips)
        df["county_name"] = county_name
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """
    Convert selected columns to numeric, coercing errors to NaN.
    """
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _save_qa_report(lines: list[str], path: Path) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------
# Step 1: Build ACS predictors
# ---------------------------------------------------------------------

def _build_acs_predictors() -> pd.DataFrame:
    """
    Fetch and construct all ACS predictor variables for ARC block groups.

    Returns a DataFrame with GEOID and all predictor columns.
    """

    # --- B25003: Occupied housing units (denominator weight) ---
    b25003_vars = ["B25003_001E"]
    print("Fetching B25003 (Tenure / occupied households)...")
    df_tenure = _fetch_acs_table_arc("B25003", b25003_vars)
    df_tenure = _to_numeric(df_tenure, b25003_vars)

    # --- B19001: Household income distribution ---
    b19001_vars = [f"B19001_{s}" for s, _, _ in B19001_BINS]
    b19001_total = "B19001_001E"
    print("Fetching B19001 (Household income)...")
    df_income = _fetch_acs_table_arc("B19001", b19001_vars + [b19001_total])
    df_income = _to_numeric(df_income, b19001_vars + [b19001_total])

    # --- B11016: Household type by household size ---
    b11016_vars = [f"B11016_{s}" for s, _ in B11016_BINS]
    b11016_total = "B11016_001E"
    print("Fetching B11016 (Household size)...")
    df_hhsize = _fetch_acs_table_arc("B11016", b11016_vars + [b11016_total])
    df_hhsize = _to_numeric(df_hhsize, b11016_vars + [b11016_total])

    # --- B11005: Households by presence of children under 18 ---
    # 001E = total households, 002E = households with children under 18
    b11005_vars = ["B11005_001E", "B11005_002E"]
    print("Fetching B11005 (Households with children)...")
    df_children = _fetch_acs_table_arc("B11005", b11005_vars)
    df_children = _to_numeric(df_children, b11005_vars)

    # --- B25024: Units in structure ---
    # 001E=total, 002E=1 detached, 003E=1 attached, 004E=2, 005E=3-4,
    # 006E=5-9, 007E=10-19, 008E=20-49, 009E=50+, 010E=mobile home,
    # 011E=boat/RV/van/etc.
    b25024_vars = [f"B25024_{i:03d}E" for i in range(1, 12)]
    print("Fetching B25024 (Units in structure)...")
    df_struct = _fetch_acs_table_arc("B25024", b25024_vars)
    df_struct = _to_numeric(df_struct, b25024_vars)

    # --- B25041: Bedrooms ---
    b25041_vars = [f"B25041_{s}" for s, _ in B25041_BINS]
    b25041_total = "B25041_001E"
    print("Fetching B25041 (Bedrooms)...")
    df_beds = _fetch_acs_table_arc("B25041", b25041_vars + [b25041_total])
    df_beds = _to_numeric(df_beds, b25041_vars + [b25041_total])

    # --- Merge all tables on GEOID ---
    df = df_tenure[["GEOID", "county_name", "state", "county", "tract", "block group", "B25003_001E"]].copy()

    for other, cols in [
        (df_income,   b19001_vars + [b19001_total]),
        (df_hhsize,   b11016_vars + [b11016_total]),
        (df_children, b11005_vars),
        (df_struct,   b25024_vars),
        (df_beds,     b25041_vars + [b25041_total]),
    ]:
        df = df.merge(other[["GEOID"] + cols], on="GEOID", how="left")

    # --- Construct E_log_income_bg ---
    # Midpoint = average of low and high for each bin
    income_total = df[b19001_total].replace(0, np.nan)
    e_log_income = pd.Series(0.0, index=df.index)
    for suffix, low, high in B19001_BINS:
        col = f"B19001_{suffix}"
        midpoint = (low + high) / 2.0
        share = df[col] / income_total
        e_log_income += share * np.log(midpoint)
    df["E_log_income_bg"] = np.where(income_total.notna(), e_log_income, np.nan)

    # --- Construct E_log_hhsize_bg ---
    hhsize_total = df[b11016_total].replace(0, np.nan)
    e_log_hhsize = pd.Series(0.0, index=df.index)
    for suffix, size_val in B11016_BINS:
        col = f"B11016_{suffix}"
        share = df[col] / hhsize_total
        e_log_hhsize += share * np.log(size_val)
    df["E_log_hhsize_bg"] = np.where(hhsize_total.notna(), e_log_hhsize, np.nan)

    # --- Construct share_households_with_children_bg ---
    all_hh = df["B11005_001E"].replace(0, np.nan)
    df["share_households_with_children_bg"] = df["B11005_002E"] / all_hh

    # --- Construct structure-type shares (B25024) ---
    total_units = df["B25024_001E"].replace(0, np.nan)
    # single detached (002E) is the omitted reference category
    df["share_single_attached_bg"] = df["B25024_003E"] / total_units
    # 2-4 units: 004E (2 units) + 005E (3-4 units)
    df["share_2_to_4_units_bg"] = (df["B25024_004E"] + df["B25024_005E"]) / total_units
    # 5-19 units: 006E (5-9) + 007E (10-19)
    df["share_5_to_19_units_bg"] = (df["B25024_006E"] + df["B25024_007E"]) / total_units
    # 20+ units: 008E (20-49) + 009E (50+)
    df["share_20plus_units_bg"] = (df["B25024_008E"] + df["B25024_009E"]) / total_units
    # mobile/other: 010E (mobile home) + 011E (boat/RV/van/etc.)
    df["share_mobile_other_bg"] = (df["B25024_010E"] + df["B25024_011E"]) / total_units

    # --- Construct expected_bedrooms_bg ---
    beds_total = df[b25041_total].replace(0, np.nan)
    e_bedrooms = pd.Series(0.0, index=df.index)
    for suffix, midpoint in B25041_BINS:
        col = f"B25041_{suffix}"
        share = df[col] / beds_total
        e_bedrooms += share * midpoint
    df["expected_bedrooms_bg"] = np.where(beds_total.notna(), e_bedrooms, np.nan)

    # --- Rename occupied households column for clarity ---
    df = df.rename(columns={"B25003_001E": "occupied_households_bg"})

    keep_cols = (
        ["GEOID", "county_name", "state", "county", "tract", "block group",
         "occupied_households_bg"]
        + PREDICTOR_COLS
    )

    return df[keep_cols].sort_values("GEOID").reset_index(drop=True)


def _predictors_qa_lines(df: pd.DataFrame) -> list[str]:
    """
    Build a QA report for the ACS predictors table.
    """
    lines = []
    lines.append("ACS Sqft Regression Predictors QA Report - Cobb County Block Groups")
    lines.append("=" * 80)
    lines.append(f"ACS year: {ACS_YEAR}")
    lines.append(f"Rows: {len(df):,}")
    lines.append(f"Counties: {df['county_name'].nunique()}")
    lines.append("")

    bad_geoid = df[df["GEOID"].astype(str).str.len() != 12]
    dup_geoid = df[df["GEOID"].duplicated(keep=False)]
    lines.append("GEOID checks:")
    lines.append(
        "PASS: All GEOIDs are 12 characters."
        if bad_geoid.empty else f"FAIL: {len(bad_geoid):,} GEOIDs not 12 characters."
    )
    lines.append(
        "PASS: No duplicate GEOIDs."
        if dup_geoid.empty else f"FAIL: {len(dup_geoid):,} duplicate GEOID rows."
    )
    lines.append("")

    lines.append("Predictor summary statistics:")
    for col in ["occupied_households_bg"] + PREDICTOR_COLS:
        if col not in df.columns:
            lines.append(f"  {col}: MISSING")
            continue
        s = df[col]
        n_null = s.isna().sum()
        lines.append(
            f"  {col}: mean={s.mean():.4f}, min={s.min():.4f}, "
            f"max={s.max():.4f}, null={n_null:,}"
        )
    lines.append("")

    lines.append("County block group counts:")
    for county_name, grp in df.groupby("county_name"):
        lines.append(f"  {county_name}: {len(grp):,} block groups")

    return lines


def run_step_build_predictors() -> None:
    """
    Fetch ACS tables and build predictor variables for all ARC block groups.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    df = _build_acs_predictors()
    df.to_csv(ACS_PREDICTORS_CSV, index=False)
    print(f"Saved ACS predictors: {ACS_PREDICTORS_CSV}")

    qa_lines = _predictors_qa_lines(df)
    _save_qa_report(qa_lines, ACS_PREDICTORS_QA_TXT)
    print(f"Saved predictors QA report: {ACS_PREDICTORS_QA_TXT}")


# ---------------------------------------------------------------------
# Step 2: Build modeling table
# ---------------------------------------------------------------------

def _load_acs_predictors() -> pd.DataFrame:
    if not ACS_PREDICTORS_CSV.exists():
        raise FileNotFoundError(
            f"ACS predictors not found: {ACS_PREDICTORS_CSV}. "
            "Run --build-predictors first."
        )
    df = pd.read_csv(ACS_PREDICTORS_CSV, dtype={"GEOID": str})
    for col in ["occupied_households_bg"] + PREDICTOR_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _load_arc_bg_res_sqft() -> pd.DataFrame:
    if not ARC_BG_RES_SQFT_CSV.exists():
        raise FileNotFoundError(
            f"ARC block group residential sqft not found: {ARC_BG_RES_SQFT_CSV}."
        )
    df = pd.read_csv(ARC_BG_RES_SQFT_CSV, dtype={"geoid": str})
    df = df.rename(columns={"geoid": "GEOID", "total_res_sqft": "total_residential_sqft_bg"})
    df["GEOID"] = df["GEOID"].astype(str).str.zfill(12)
    df["total_residential_sqft_bg"] = pd.to_numeric(
        df["total_residential_sqft_bg"], errors="coerce"
    ).fillna(0)
    return df[["GEOID", "total_residential_sqft_bg"]]


def _build_modeling_table() -> pd.DataFrame:
    """
    Join parcel-derived sqft with ACS predictors and compute the dependent variable.

    Dependent variable:
        log(total_residential_sqft_bg / occupied_households_bg)

    Only block groups with occupied_households_bg > 0 and
    total_residential_sqft_bg > 0 are included.
    """
    df_sqft = _load_arc_bg_res_sqft()
    df_acs = _load_acs_predictors()

    df = df_acs.merge(df_sqft, on="GEOID", how="left")
    df["total_residential_sqft_bg"] = df["total_residential_sqft_bg"].fillna(0)

    # Compute dependent variable
    valid = (df["occupied_households_bg"] > 0) & (df["total_residential_sqft_bg"] > 0)
    df[Y_COL] = np.where(
        valid,
        np.log(df["total_residential_sqft_bg"] / df["occupied_households_bg"]),
        np.nan,
    )

    return df.sort_values("GEOID").reset_index(drop=True)


def _modeling_table_qa_lines(df: pd.DataFrame) -> list[str]:
    lines = []
    lines.append("ACS Sqft Regression Modeling Table QA Report - Cobb County Block Groups")
    lines.append("=" * 80)
    lines.append(f"ACS year: {ACS_YEAR}")
    lines.append(f"Total block groups: {len(df):,}")

    n_valid = df[Y_COL].notna().sum()
    n_zero_sqft = (df["total_residential_sqft_bg"] == 0).sum()
    n_zero_hh = (df["occupied_households_bg"] == 0).sum()
    n_null_y = df[Y_COL].isna().sum()

    lines.append(f"Block groups with valid dependent variable: {n_valid:,}")
    lines.append(f"Block groups with zero residential sqft: {n_zero_sqft:,}")
    lines.append(f"Block groups with zero occupied households: {n_zero_hh:,}")
    lines.append(f"Block groups excluded (null dependent variable): {n_null_y:,}")
    lines.append("")

    lines.append(f"Dependent variable ({Y_COL}) summary:")
    y = df[Y_COL].dropna()
    lines.append(f"  mean={y.mean():.4f}, std={y.std():.4f}, "
                 f"min={y.min():.4f}, max={y.max():.4f}")
    lines.append("")

    lines.append("Predictor null counts (valid rows only):")
    df_valid = df[df[Y_COL].notna()]
    for col in PREDICTOR_COLS:
        n_null = df_valid[col].isna().sum()
        lines.append(f"  {col}: {n_null:,} nulls")

    return lines


def run_step_build_modeling_table() -> None:
    """
    Join sqft and ACS predictors, compute dependent variable, save modeling table.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    df = _build_modeling_table()
    df.to_csv(MODELING_TABLE_CSV, index=False)
    print(f"Saved modeling table: {MODELING_TABLE_CSV}")

    qa_lines = _modeling_table_qa_lines(df)
    _save_qa_report(qa_lines, MODELING_TABLE_QA_TXT)
    print(f"Saved modeling table QA report: {MODELING_TABLE_QA_TXT}")


# ---------------------------------------------------------------------
# Step 3: Fit regression
# ---------------------------------------------------------------------

def _load_modeling_table() -> pd.DataFrame:
    if not MODELING_TABLE_CSV.exists():
        raise FileNotFoundError(
            f"Modeling table not found: {MODELING_TABLE_CSV}. "
            "Run --build-modeling-table first."
        )
    df = pd.read_csv(MODELING_TABLE_CSV, dtype={"GEOID": str})
    for col in [Y_COL, "occupied_households_bg", "total_residential_sqft_bg"] + PREDICTOR_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _fit_wls(
    df: pd.DataFrame,
    y_col: str,
    x_cols: list[str],
    weight_col: str,
    model_name: str,
) -> dict:
    """
    Fit weighted least squares using numpy and return summary statistics.

    Weights are applied by multiplying both X and y by sqrt(weight).
    """
    needed = [y_col, weight_col] + x_cols
    model_df = df.dropna(subset=needed).copy()
    model_df = model_df[model_df[weight_col] > 0].copy()

    y = model_df[y_col].to_numpy(dtype=float)
    x = model_df[x_cols].to_numpy(dtype=float)
    w = model_df[weight_col].to_numpy(dtype=float)

    sqrt_w = np.sqrt(w)
    x_design = np.column_stack([np.ones(len(model_df)), x])
    coefficient_names = ["intercept"] + x_cols

    # Weight the design matrix and response
    xw = x_design * sqrt_w[:, np.newaxis]
    yw = y * sqrt_w

    coefficients, _, rank, _ = np.linalg.lstsq(xw, yw, rcond=None)

    predicted = x_design @ coefficients
    residual = y - predicted

    n_obs = len(y)
    n_params = x_design.shape[1]

    # Weighted fit statistics
    sse_w = float(np.sum(w * residual ** 2))
    tss_w = float(np.sum(w * (y - np.average(y, weights=w)) ** 2))
    r_squared = 1 - (sse_w / tss_w) if tss_w != 0 else np.nan

    if n_obs > n_params and tss_w != 0:
        adj_r_squared = 1 - (
            (sse_w / (n_obs - n_params)) / (tss_w / (n_obs - 1))
        )
    else:
        adj_r_squared = np.nan

    sse = float(np.sum(residual ** 2))
    rmse = float(np.sqrt(sse / n_obs)) if n_obs > 0 else np.nan
    mae = float(np.mean(np.abs(residual))) if n_obs > 0 else np.nan

    if n_obs > n_params:
        sigma2 = sse_w / (n_obs - n_params)
        xtx_inv = np.linalg.pinv(xw.T @ xw)
        standard_errors = np.sqrt(np.diag(sigma2 * xtx_inv))
    else:
        standard_errors = np.full(len(coefficients), np.nan)

    t_stats = np.where(
        standard_errors != 0, coefficients / standard_errors, np.nan
    )

    coef_df = pd.DataFrame(
        {
            "term": coefficient_names,
            "coefficient": coefficients,
            "std_error": standard_errors,
            "t_stat": t_stats,
        }
    )

    # Smearing factor for back-transformation: exp(predicted_log_sqft) * smearing
    smearing_factor = float(np.mean(np.exp(residual)))

    prediction_df = model_df[["GEOID", y_col, weight_col]].copy()
    prediction_df["predicted_log_sqft_per_hh"] = predicted
    prediction_df["residual"] = residual
    prediction_df["predicted_sqft_per_hh"] = np.exp(predicted) * smearing_factor

    return {
        "model_name": model_name,
        "y_col": y_col,
        "x_cols": x_cols,
        "weight_col": weight_col,
        "n_obs": n_obs,
        "n_params": n_params,
        "rank": int(rank),
        "r_squared": r_squared,
        "adj_r_squared": adj_r_squared,
        "rmse": rmse,
        "mae": mae,
        "smearing_factor": smearing_factor,
        "coefficients": coef_df,
        "predictions": prediction_df,
    }


def _format_regression_report(result: dict) -> list[str]:
    lines = []
    lines.append(result["model_name"])
    lines.append("=" * 80)
    lines.append(f"Dependent variable: {result['y_col']}")
    lines.append(f"Weight: {result['weight_col']}")
    lines.append(f"Predictors: {', '.join(result['x_cols'])}")
    lines.append(f"Observations: {result['n_obs']:,}")
    lines.append(f"Parameters: {result['n_params']:,}")
    lines.append(f"Design matrix rank: {result['rank']:,}")
    lines.append(f"R-squared (weighted): {result['r_squared']:.6f}")
    lines.append(f"Adjusted R-squared (weighted): {result['adj_r_squared']:.6f}")
    lines.append(f"RMSE (unweighted): {result['rmse']:.6f}")
    lines.append(f"MAE (unweighted): {result['mae']:.6f}")
    lines.append(f"Smearing factor: {result['smearing_factor']:.6f}")
    lines.append("")
    lines.append("Coefficients:")
    lines.append(f"  {'Term':<40} {'Coefficient':>14} {'Std Error':>12} {'t-stat':>10}")
    lines.append("  " + "-" * 78)
    for _, row in result["coefficients"].iterrows():
        lines.append(
            f"  {row['term']:<40} {row['coefficient']:>14.6f} "
            f"{row['std_error']:>12.6f} {row['t_stat']:>10.3f}"
        )
    lines.append("")
    lines.append(
        "Back-transformation: predicted_sqft_h = exp(predicted_log_sqft_h) * smearing_factor"
    )
    return lines


def _build_diagnostics(result: dict) -> pd.DataFrame:
    """
    Build a per-block-group diagnostics DataFrame from regression predictions.
    """
    pred_df = result["predictions"].copy()
    pred_df["model_name"] = result["model_name"]
    pred_df["abs_residual"] = pred_df["residual"].abs()
    pred_df["abs_pct_error"] = np.where(
        pred_df[result["y_col"]] != 0,
        pred_df["abs_residual"] / pred_df[result["y_col"]].abs(),
        np.nan,
    )
    return pred_df


def run_step_fit_regression() -> None:
    """
    Load modeling table, fit weighted OLS, save results and diagnostics.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    df = _load_modeling_table()
    df_reg = df[df[Y_COL].notna()].copy()

    # Drop rows with any null predictor
    df_reg = df_reg.dropna(subset=PREDICTOR_COLS + ["occupied_households_bg"])

    print(f"Fitting regression on {len(df_reg):,} block groups...")

    result = _fit_wls(
        df=df_reg,
        y_col=Y_COL,
        x_cols=PREDICTOR_COLS,
        weight_col="occupied_households_bg",
        model_name="ACS Residential Sqft Regression - Cobb County Block Groups (WLS)",
    )

    report_lines = _format_regression_report(result)
    _save_qa_report(report_lines, REGRESSION_RESULTS_TXT)
    print(f"Saved regression results: {REGRESSION_RESULTS_TXT}")

    diagnostics = _build_diagnostics(result)
    diagnostics.to_csv(REGRESSION_DIAGNOSTICS_CSV, index=False)
    print(f"Saved regression diagnostics: {REGRESSION_DIAGNOSTICS_CSV}")

    # Print summary to console
    for line in report_lines:
        print(line)


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "ACS residential square footage regression for Cobb County block groups. "
            "Steps: build-predictors -> build-modeling-table -> fit-regression."
        )
    )
    parser.add_argument(
        "--build-predictors",
        action="store_true",
        help="Fetch ACS tables and build predictor variables for all ARC block groups.",
    )
    parser.add_argument(
        "--build-modeling-table",
        action="store_true",
        help="Join parcel sqft with ACS predictors and compute dependent variable.",
    )
    parser.add_argument(
        "--fit-regression",
        action="store_true",
        help="Fit weighted OLS regression and save results.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all steps in sequence.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    run_all = args.all or not (
        args.build_predictors or args.build_modeling_table or args.fit_regression
    )

    if args.build_predictors or run_all:
        run_step_build_predictors()

    if args.build_modeling_table or run_all:
        run_step_build_modeling_table()

    if args.fit_regression or run_all:
        run_step_fit_regression()
