import requests
import pandas as pd
import time

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

    return pd.concat(rows, ignore_index=True)

# Download and save all tables
for table, label in tables.items():
    print(f"Downloading {table} ({label}) ...")
    df = fetch_table(table)
    df.to_csv(f"ARC_{label}_2023_BG.csv", index=False)

print("Done.")
