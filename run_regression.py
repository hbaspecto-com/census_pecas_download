#!/usr/bin/env python3

"""
run_regression.py

Regression workflow for block-group residential square footage modeling.

Step 1: Define the initial geography.

Initial scope:
- Cobb County, Georgia
- Census block groups
- 2024 ACS 5-year Detailed Tables
"""

from pathlib import Path
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


# ---------------------------------------------------------------------
# Geography helpers
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

    The Census API requires at least one data variable. We request B11016_001E,
    total households from the household size table, as a useful sanity-check field.
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

    # Keep geography columns plus one sanity-check ACS field.
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
# QA
# ---------------------------------------------------------------------

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

    lines.append("Columns:")
    for col in df.columns:
        lines.append(f"  - {col}")
    lines.append("")

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

    if len(duplicate_geoids) == 0:
        lines.append("PASS: No duplicate GEOIDs.")
    else:
        lines.append(f"FAIL: Found {len(duplicate_geoids):,} duplicate GEOIDs.")

    if bad_geoid_length.empty:
        lines.append("PASS: All GEOIDs are 12 characters.")
    else:
        lines.append(f"FAIL: Found {len(bad_geoid_length):,} GEOIDs not 12 characters.")

    missing_counties = expected_counties - observed_counties
    extra_counties = observed_counties - expected_counties

    if not missing_counties:
        lines.append("PASS: No expected counties are missing.")
    else:
        lines.append(f"FAIL: Missing expected counties: {sorted(missing_counties)}")

    if not extra_counties:
        lines.append("PASS: No unexpected counties are present.")
    else:
        lines.append(f"FAIL: Unexpected counties present: {sorted(extra_counties)}")

    lines.append("")

    # Cobb-specific check when applicable.
    if expected_counties == {COBB_COUNTY_FIPS}:
        non_cobb_geoids = df[~df["GEOID"].astype(str).str.startswith("13067")]
        if non_cobb_geoids.empty:
            lines.append("PASS: All Cobb GEOIDs start with 13067.")
        else:
            lines.append(
                f"FAIL: Found {len(non_cobb_geoids):,} rows whose GEOID does not start with 13067."
            )

    return lines


def save_qa_report(lines: list[str], path: Path) -> None:
    """
    Save QA report lines to a text file.
    """
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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

    output_csv = OUTPUT_DIR / "block_groups_cobb_2024.csv"
    qa_txt = OUTPUT_DIR / "geography_qa_cobb_2024.txt"

    bg_df.to_csv(output_csv, index=False)

    qa_lines = geography_qa(
        bg_df,
        expected_counties=set(counties.keys()),
    )
    save_qa_report(qa_lines, qa_txt)

    print("")
    print(f"Saved block group geography to: {output_csv}")
    print(f"Saved geography QA report to: {qa_txt}")
    print("")
    print("\n".join(qa_lines))


if __name__ == "__main__":
    run_step_1_cobb()