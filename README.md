# Census ACS Downloader for ARC Block Groups

This project downloads selected 2023 ACS 5-year tables from the U.S. Census API for Atlanta Regional Commission (ARC) counties at the block group level, then writes them to CSV files.

## What it does

- Retrieves all variables from specified ACS table groups (e.g., B25003 Tenure, B25024 Units in Structure).
- Fetches data per county in the ARC region for all block groups.
- Handles API pagination by chunking variable requests.
- Merges chunks horizontally by geography keys (state, county, tract, block group).
- Saves one CSV per table, e.g.:
  - ARC_UnitsInStructure_2023_BG.csv
  - ARC_Tenure_2023_BG.csv

Columns include:
- NAME: human-readable geography label
- ACS estimate and margin-of-error columns for each variable in the table (e.g., B25003_001E, B25003_001M, …)
- state, county, tract, block group: geographic identifiers

Example output file: ARC_Tenure_2023_BG.csv.

## Requirements

- Python 3.13+
- virtualenv (recommended)
- Packages:
  - pandas
  - requests

Use requirements.txt for versions.

## Setup

1. Create and activate a virtual environment.
   - macOS/Linux:
     - python3 -m venv .venv
     - source .venv/bin/activate
   - Windows:
     - python -m venv .venv
     - .venv\Scripts\activate

2. Install dependencies:
   - pip install -r requirements.txt

## Usage

- Run the downloader:
  - python download_acs.py

This will generate CSV files in the project directory for each configured table.

## Configuring tables and geography

- Edit the tables dictionary in download_acs.py to add/remove ACS groups.
- Update arc_counties and state to target other states/counties (FIPS codes).

## Notes and limits

- The Census API limits the number of variables per request; the script chunks variables to stay within limits.
- The script includes basic retry logic for transient API errors.
- Merging relies on geography keys: state, county, tract, block group. Do not drop these columns before merging.

## Troubleshooting

- KeyError on merge (e.g., 'state'):
  - Ensure you aren’t dropping geography key columns before merging chunks. Keep state, county, tract, block group in all parts and merge on these keys.
- API errors or timeouts:
  - The script retries automatically. If persistent, try again later or reduce the number of tables.

## License

Apache Version 2.0
