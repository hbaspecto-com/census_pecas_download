# Step 2 Inventory: Parcel/Building Data

## Source Data Location

Parcel data was copied from the Windows machine to the Linux repo.

Original Windows source:

`C:\ARCPECAS\RegionalParcelDataSet2024`

Linux repo destination:

`inputs/RegionalParcelDataSet2024`

Copied contents include:

- `inputs/RegionalParcelDataSet2024/Codebooks - Current Version`
- `inputs/RegionalParcelDataSet2024/RPD24_V2.gdb`

Copy verification:

| Check | Source | Destination | Result |
|---|---:|---:|---|
| File count | 185 | 185 | PASS |
| Total file bytes | 2,780,822,319 | 2,780,822,319 | PASS |

Note: apparent size differences reported by operating-system tools appear to be filesystem/reporting differences, not a failed copy.

## Data Format

The parcel data is stored in an Esri File Geodatabase:

`inputs/RegionalParcelDataSet2024/RPD24_V2.gdb`

The geodatabase can be opened on Linux with GDAL/OGR using the `OpenFileGDB` driver.

`ogrinfo` reports repeated `ERROR 1` messages from `filegdbtable.cpp`, but still opens the geodatabase successfully and lists layers.

## Codebooks / Documentation

Available documentation files:

- `inputs/RegionalParcelDataSet2024/Codebooks - Current Version/ATTOM_DataDictionary.xlsx`
- `inputs/RegionalParcelDataSet2024/Codebooks - Current Version/RPD24_V2 Codebook and Documentation.md`

Temporary Office lock file present and ignored:

- `inputs/RegionalParcelDataSet2024/Codebooks - Current Version/~$ATTOM_DataDictionary.xlsx`

## Geodatabase Layers

Layers listed by `ogrinfo`:

- `RPD24_V2_13057`
- `RPD24_V2_13063`
- `RPD24_V2_13067`
- `RPD24_V2_13077`
- `RPD24_V2_13085`
- `RPD24_V2_13089`
- `RPD24_V2_13097`
- `RPD24_V2_13113`
- `RPD24_V2_13117`
- `RPD24_V2_13135`
- `RPD24_V2_13139`
- `RPD24_V2_13151`
- `RPD24_V2_13217`
- `RPD24_V2_13223`
- `RPD24_V2_13247`
- `RPD24_V2_13255`
- `RPD24_V2_13297`
- `RPD24_V2_13121`
- `RPD24_V2_5CC`
- `RPD24_V2`
- `RPD24_V2_13013`
- `RPD24_V2_13015`
- `RPD24_V2_13045`

The Cobb County layer is:

`RPD24_V2_13067`

Cobb County FIPS is `13067`.

## Cobb County Layer Summary

Layer:

`RPD24_V2_13067`

Basic properties from `ogrinfo -so`:

| Property | Value |
|---|---|
| Geometry type | 3D Measured Multi Polygon |
| Feature count | 264,126 |
| Extent | (-84.739678, 33.743865) - (-84.375227, 34.081791) |
| CRS | WGS 84 / EPSG:4326 |
| FID column | OBJECTID |
| Geometry column | Shape |

## Cobb County Fields

Fields reported by `ogrinfo -so`:

| Field | Type |
|---|---|
| ARCID_MR | String |
| apn | String |
| addrline1 | String |
| city | String |
| state | String |
| zip5 | String |
| CompanyFla | String |
| PartyOwner | String |
| PartyOwn_1 | String |
| PartyOwn_2 | String |
| PartyOwn_3 | String |
| ContactOwn | String |
| ContactO_1 | String |
| ContactO_2 | String |
| ContactO_3 | Integer |
| TaxMarketV | Integer |
| TaxMarke_1 | Integer |
| AreaBuildi | Integer |
| YearBuilt | Integer |
| ParcelAcreage_MR | Real |
| SitusState | Integer |
| latitude | Real |
| longitude | Real |
| ZonedCodeL | String |
| ZoningTranche_MR | String |
| ZoningJuris_MR | String |
| PropertyUseStandardized | Integer |
| LUTranche_MR | String |
| LUType_MR | String |
| PECASResiTranche_MR | String |
| Shape_Length | Real |
| Shape_Area | Real |

## Candidate Modeling Fields

Initial candidate fields for the regression workflow:

| Purpose | Candidate Field | Notes |
|---|---|---|
| Unique parcel/building identifier | `apn` | Parcel/account identifier candidate. Need duplicate check. |
| ARC/internal identifier | `ARCID_MR` | May be useful for traceability. Need duplicate check. |
| Residential building square footage | `AreaBuildi` | Candidate dependent-variable source. Need codebook definition and QA. |
| Year built | `YearBuilt` | Optional QA/control field. |
| Parcel acreage | `ParcelAcreage_MR` | Optional QA field. |
| Latitude | `latitude` | Candidate point coordinate if needed. |
| Longitude | `longitude` | Candidate point coordinate if needed. |
| Property use code | `PropertyUseStandardized` | Candidate residential filter field. Need codebook values. |
| Land-use tranche | `LUTranche_MR` | Candidate residential filter/diagnostic field. |
| Land-use type | `LUType_MR` | Candidate residential filter/diagnostic field. |
| PECAS residential tranche | `PECASResiTranche_MR` | Likely residential category/filter field. Need value inventory. |
| Geometry | `Shape` | Parcel polygon geometry. Can be used for centroid-based spatial assignment. |

## Current Understanding

- The source parcel/building data is available for Cobb County and multiple other counties in the same geodatabase.
- The first-pass Cobb layer has 264,126 polygon features.
- The data appears to include parcel polygons rather than building footprints.
- No obvious block group GEOID field appeared in the Cobb layer schema.
- The data has both polygon geometry and latitude/longitude fields.
- For block-group assignment, the likely first-pass method is a centroid-based spatial join.
- For the dependent variable, the likely first-pass square-footage field is `AreaBuildi`, pending codebook confirmation.
- For identifying residential records, the likely candidate fields are `PECASResiTranche_MR`, `LUType_MR`, `LUTranche_MR`, and/or `PropertyUseStandardized`, pending codebook confirmation and value counts.

## Commands Run So Far

Check remote `inputs` folder:

```bash
ssh sja@whitemud.hbaspecto.com "ls -ld /nfs/home/sja/repos/census_pecas_download/inputs"
```

Copy parcel data from Windows Git Bash:

```bash
scp -r "/c/ARCPECAS/RegionalParcelDataSet2024" sja@whitemud.hbaspecto.com:/nfs/home/sja/repos/census_pecas_download/inputs/
```

Verify source file count:

```bash
find "/c/ARCPECAS/RegionalParcelDataSet2024" -type f | wc -l
```

Verify destination file count:

```bash
ssh sja@whitemud.hbaspecto.com "find /nfs/home/sja/repos/census_pecas_download/inputs/RegionalParcelDataSet2024 -type f | wc -l"
```

Verify source total bytes:

```bash
find "/c/ARCPECAS/RegionalParcelDataSet2024" -type f -printf "%s\n" | awk '{s+=$1} END {print s}'
```

Verify destination total bytes:

```bash
ssh sja@whitemud.hbaspecto.com "find /nfs/home/sja/repos/census_pecas_download/inputs/RegionalParcelDataSet2024 -type f -printf '%s\n' | awk '{s+=\$1} END {print s}'"
```

List copied directories:

```bash
find inputs/RegionalParcelDataSet2024 -maxdepth 2 -type d | sort
```

List geodatabase layers:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb
```

Inspect Cobb layer schema:

```bash
ogrinfo -so inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067
```

List codebook files:

```bash
find "inputs/RegionalParcelDataSet2024/Codebooks - Current Version" -maxdepth 2 -type f | sort
```

## Next Inventory Checks

### 1. Review codebook definitions

Search key fields in the Markdown codebook:

```bash
grep -in "AreaBuildi\|PECASResiTranche\|PropertyUseStandardized\|LUTranche\|LUType\|apn\|ARCID" \
  "inputs/RegionalParcelDataSet2024/Codebooks - Current Version/RPD24_V2 Codebook and Documentation.md"
```

Read the first part of the Markdown codebook:

```bash
sed -n '1,220p' "inputs/RegionalParcelDataSet2024/Codebooks - Current Version/RPD24_V2 Codebook and Documentation.md"
```

### 2. Inventory residential classification values

Residential tranche values:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT PECASResiTranche_MR, COUNT(*) AS n FROM RPD24_V2_13067 GROUP BY PECASResiTranche_MR ORDER BY n DESC"
```

Land-use tranche values:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT LUTranche_MR, COUNT(*) AS n FROM RPD24_V2_13067 GROUP BY LUTranche_MR ORDER BY n DESC"
```

Land-use type values:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT LUType_MR, COUNT(*) AS n FROM RPD24_V2_13067 GROUP BY LUType_MR ORDER BY n DESC"
```

Property-use standardized values:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT PropertyUseStandardized, COUNT(*) AS n FROM RPD24_V2_13067 GROUP BY PropertyUseStandardized ORDER BY n DESC"
```

### 3. Inventory square footage

Overall `AreaBuildi` distribution:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT COUNT(*) AS n, SUM(CASE WHEN AreaBuildi IS NULL THEN 1 ELSE 0 END) AS missing_areabuildi, SUM(CASE WHEN AreaBuildi = 0 THEN 1 ELSE 0 END) AS zero_areabuildi, MIN(AreaBuildi) AS min_areabuildi, MAX(AreaBuildi) AS max_areabuildi, AVG(AreaBuildi) AS avg_areabuildi FROM RPD24_V2_13067"
```

`AreaBuildi` by residential tranche:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT PECASResiTranche_MR, COUNT(*) AS n, SUM(CASE WHEN AreaBuildi IS NULL THEN 1 ELSE 0 END) AS missing_areabuildi, SUM(CASE WHEN AreaBuildi = 0 THEN 1 ELSE 0 END) AS zero_areabuildi, MIN(AreaBuildi) AS min_areabuildi, MAX(AreaBuildi) AS max_areabuildi, AVG(AreaBuildi) AS avg_areabuildi FROM RPD24_V2_13067 GROUP BY PECASResiTranche_MR ORDER BY n DESC"
```

### 4. Check candidate ID uniqueness

Check `apn` uniqueness:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT COUNT(*) AS n, COUNT(DISTINCT apn) AS distinct_apn, COUNT(*) - COUNT(DISTINCT apn) AS duplicate_apn_count FROM RPD24_V2_13067"
```

Check `ARCID_MR` uniqueness:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT COUNT(*) AS n, COUNT(DISTINCT ARCID_MR) AS distinct_arcid_mr, COUNT(*) - COUNT(DISTINCT ARCID_MR) AS duplicate_arcid_mr_count FROM RPD24_V2_13067"
```

## Open Questions

- What is the exact definition of `AreaBuildi`?
- Does `AreaBuildi` represent heated living area, total building area, improvement area, or another concept?
- Which field should define residential records?
- Should the first-pass residential filter use `PECASResiTranche_MR`, `LUType_MR`, `LUTranche_MR`, `PropertyUseStandardized`, or a combination?
- Are multifamily/apartment records included and identifiable?
- Are mixed-use records included, and if so can residential square footage be isolated?
- Does the parcel data include a block group GEOID field? Initial field list does not show an obvious GEOID field.
- Should block-group assignment use parcel polygon centroid, provided latitude/longitude, or another method?
- Are `apn` or `ARCID_MR` unique within the Cobb layer?
- How many records have missing, zero, or extreme `AreaBuildi` values?

## Codebook Findings

Key field definitions from `RPD24_V2 Codebook and Documentation.md`:

| Field | Codebook Definition | Initial Interpretation |
|---|---|---|
| `ARCID_MR` | Internal Parcel ID for ARC Use | Internal ARC parcel identifier. Useful for traceability and duplicate checks. |
| `apn` | Parcel ID from County Tax Assessor | County assessor parcel identifier. Candidate parcel ID. |
| `AreaBuildi` | Combined Square Footage of All Climate Controlled Structures | Strong candidate square-footage field for the dependent variable. Represents climate-controlled structure area, not parcel area. |
| `PropertyUseStandardized` | ATTOM-Derived Land Use Code - Methodology Unknown | Candidate land-use field, but methodology is unknown. Use cautiously. |
| `LUTranche_MR` | Universal Land Use Category | Candidate broad land-use classification field. |
| `LUType_MR` | Use-Specific Land Use Subcategory | Candidate detailed land-use classification field. |
| `PECASResiTranche_MR` | PECAS-Specific Residential Land Use Categories | Strong candidate residential category/filter field. |

Additional codebook notes found:

- `LUTranche_MR` includes `Residential`.
- `LUType_MR`, within `LUTranche_MR = Residential`, includes `Single Family Residential`.

## Preliminary Field Decisions

### Square-footage field

Use `AreaBuildi` as the first-pass square-footage field, pending QA.

Working definition:

```text
res_sqft = AreaBuildi
```

Rationale:

- Codebook defines `AreaBuildi` as combined square footage of all climate-controlled structures.
- This is closer to the regression target than parcel acreage, market value, or geometry area.
- Need to check missing, zero, and extreme values before finalizing.

### Residential filter fields

Primary residential-filter candidates:

1. `PECASResiTranche_MR`
2. `LUTranche_MR`
3. `LUType_MR`

Use `PropertyUseStandardized` only as a supporting diagnostic field for now because the codebook notes the ATTOM-derived methodology is unknown.

## Updated Open Questions

- What values appear in `PECASResiTranche_MR` for Cobb County?
- Are all records with residential square footage captured by `LUTranche_MR = Residential`?
- Does `PECASResiTranche_MR` distinguish single-family, multifamily, and/or other residential categories?
- Should mixed-use parcels be included or excluded in the first pass?
- Do non-residential parcels have nonzero `AreaBuildi`, and should they be excluded before aggregation?
- How many residential records have missing or zero `AreaBuildi`?
- Are there extreme `AreaBuildi` values that need review?
```

## `PECASResiTranche_MR` Value Inventory

Cobb layer: `RPD24_V2_13067`

Command:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT PECASResiTranche_MR, COUNT(*) AS n FROM RPD24_V2_13067 GROUP BY PECASResiTranche_MR ORDER BY n DESC"
```

Notes:

- GDAL/OGR printed repeated `filegdbtable.cpp` errors but completed the query successfully.
- GDAL/OGR also printed a polygon organization warning. The query result is non-spatial (`Geometry: None`) and appears usable for attribute inventory.

Results:

| `PECASResiTranche_MR` | Count |
|---|---:|
| SFR LESS THAN 1 ACRE | 200,727 |
| CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX | 22,413 |
| NOT RESIDENTIAL | 16,871 |
| SFR 1 ACRE OR MORE | 12,314 |
| VACANT RESIDENTIAL | 11,095 |
| MFR LESS THAN 3 FLOORS | 370 |
| MFR 3 FLOORS OR MORE | 183 |
| MANUFACTURED RESIDENTIAL | 153 |

Total records represented:

| Check | Count |
|---|---:|
| Sum of category counts | 264,126 |
| Cobb layer feature count | 264,126 |
| Result | PASS |

## Preliminary Residential Filter Decision

For the first-pass total residential square-footage dependent variable, include these `PECASResiTranche_MR` categories:

- `SFR LESS THAN 1 ACRE`
- `SFR 1 ACRE OR MORE`
- `CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX`
- `MFR LESS THAN 3 FLOORS`
- `MFR 3 FLOORS OR MORE`
- `MANUFACTURED RESIDENTIAL`

Exclude these categories from the first-pass residential square-footage aggregation:

- `NOT RESIDENTIAL`
- `VACANT RESIDENTIAL`

Rationale:

- `NOT RESIDENTIAL` should not contribute to residential square footage.
- `VACANT RESIDENTIAL` may represent residential land with no residential structure; exclude from the first pass unless later QA shows meaningful nonzero residential building square footage.
- Multifamily and manufactured residential should be included because the target is total residential building square footage, not only single-family square footage.

Potential first-pass filter:

```sql
PECASResiTranche_MR IN (
  'SFR LESS THAN 1 ACRE',
  'SFR 1 ACRE OR MORE',
  'CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX',
  'MFR LESS THAN 3 FLOORS',
  'MFR 3 FLOORS OR MORE',
  'MANUFACTURED RESIDENTIAL'
)
```

## Residential Category Notes

The `PECASResiTranche_MR` field appears to support useful diagnostic splits:

| Broad Group | Categories |
|---|---|
| Single-family residential | `SFR LESS THAN 1 ACRE`, `SFR 1 ACRE OR MORE` |
| Condo/townhome/small attached | `CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX` |
| Multifamily | `MFR LESS THAN 3 FLOORS`, `MFR 3 FLOORS OR MORE` |
| Manufactured residential | `MANUFACTURED RESIDENTIAL` |
| Vacant residential land | `VACANT RESIDENTIAL` |
| Non-residential | `NOT RESIDENTIAL` |

Possible later dependent variables:

- `total_res_sqft`
- `sfr_res_sqft`
- `condo_townhome_duplex_triplex_quadplex_sqft`
- `mfr_res_sqft`
- `manufactured_res_sqft`


## `AreaBuildi` Overall Inventory

Cobb layer: `RPD24_V2_13067`

Command:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT COUNT(*) AS n, SUM(CASE WHEN AreaBuildi IS NULL THEN 1 ELSE 0 END) AS missing_areabuildi, SUM(CASE WHEN AreaBuildi = 0 THEN 1 ELSE 0 END) AS zero_areabuildi, MIN(AreaBuildi) AS min_areabuildi, MAX(AreaBuildi) AS max_areabuildi, AVG(AreaBuildi) AS avg_areabuildi FROM RPD24_V2_13067"
```

Results:

| Metric | Value |
|---|---:|
| Records | 264,126 |
| Missing `AreaBuildi` | 0 |
| Zero `AreaBuildi` | 16,226 |
| Minimum `AreaBuildi` | 0 |
| Maximum `AreaBuildi` | 3,929,999 |
| Average `AreaBuildi` | 3,097.45176165921 |

Initial interpretation:

- `AreaBuildi` is populated for all Cobb records.
- Zero-square-foot records exist and need category-level review.
- Some zero-square-foot records are expected if they correspond to `VACANT RESIDENTIAL`.
- The maximum value is very large and should be reviewed as a potential outlier or a legitimate large multifamily/commercial/institutional structure.
- For residential aggregation, zero `AreaBuildi` records should likely contribute `0` rather than be treated as missing.
- For QA, records with extreme nonzero `AreaBuildi` should be listed separately before modeling.

Updated QA questions:

- How many zero `AreaBuildi` records are in each `PECASResiTranche_MR` category?
- Are any included residential categories dominated by zero `AreaBuildi` values?
- Which category contains the maximum `AreaBuildi` value?
- What are the largest residential `AreaBuildi` records?

## `AreaBuildi` by `PECASResiTranche_MR`

Cobb layer: `RPD24_V2_13067`

Command:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT PECASResiTranche_MR, COUNT(*) AS n, SUM(CASE WHEN AreaBuildi IS NULL THEN 1 ELSE 0 END) AS missing_areabuildi, SUM(CASE WHEN AreaBuildi = 0 THEN 1 ELSE 0 END) AS zero_areabuildi, MIN(AreaBuildi) AS min_areabuildi, MAX(AreaBuildi) AS max_areabuildi, AVG(AreaBuildi) AS avg_areabuildi FROM RPD24_V2_13067 GROUP BY PECASResiTranche_MR ORDER BY n DESC"
```

Results:

| `PECASResiTranche_MR` | Records | Missing `AreaBuildi` | Zero `AreaBuildi` | Min `AreaBuildi` | Max `AreaBuildi` | Avg `AreaBuildi` |
|---|---:|---:|---:|---:|---:|---:|
| SFR LESS THAN 1 ACRE | 200,727 | 0 | 357 | 0 | 124,101 | 2,247.64133375181 |
| CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX | 22,413 | 0 | 28 | 0 | 258,605 | 1,534.14656672467 |
| NOT RESIDENTIAL | 16,871 | 0 | 5,632 | 0 | 3,929,999 | 13,135.3592555272 |
| SFR 1 ACRE OR MORE | 12,314 | 0 | 105 | 0 | 69,950 | 2,784.97588111093 |
| VACANT RESIDENTIAL | 11,095 | 0 | 9,948 | 0 | 156,816 | 238.323118521857 |
| MFR LESS THAN 3 FLOORS | 370 | 0 | 0 | 648 | 643,086 | 78,257.972972973 |
| MFR 3 FLOORS OR MORE | 183 | 0 | 3 | 0 | 733,450 | 246,283.775956284 |
| MANUFACTURED RESIDENTIAL | 153 | 0 | 153 | 0 | 0 | 0 |

## Square-Footage QA Interpretation

Key findings:

- `AreaBuildi` is non-missing for all records in every `PECASResiTranche_MR` category.
- Most zero `AreaBuildi` records are in:
  - `VACANT RESIDENTIAL`: 9,948 zero records
  - `NOT RESIDENTIAL`: 5,632 zero records
- Residential categories other than vacant/manufactured have relatively few zero-square-foot records.
- `MANUFACTURED RESIDENTIAL` has 153 records and all have `AreaBuildi = 0`.
- The largest overall `AreaBuildi` value is in `NOT RESIDENTIAL`, not in a residential category.
- The largest residential-category values are:
  - `MFR 3 FLOORS OR MORE`: 733,450
  - `MFR LESS THAN 3 FLOORS`: 643,086
  - `CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX`: 258,605
  - `SFR LESS THAN 1 ACRE`: 124,101
  - `SFR 1 ACRE OR MORE`: 69,950
  - `VACANT RESIDENTIAL`: 156,816

## Updated Residential Filter Decision

For the first-pass `total_res_sqft` dependent variable, include built residential categories:

- `SFR LESS THAN 1 ACRE`
- `SFR 1 ACRE OR MORE`
- `CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX`
- `MFR LESS THAN 3 FLOORS`
- `MFR 3 FLOORS OR MORE`

Exclude from first-pass built residential square footage:

- `NOT RESIDENTIAL`
- `VACANT RESIDENTIAL`
- `MANUFACTURED RESIDENTIAL`

Rationale:

- `NOT RESIDENTIAL` is outside the target concept.
- `VACANT RESIDENTIAL` mostly has zero building area and appears to represent residential land rather than built residential structures. Some records have nonzero `AreaBuildi`, so these should be reviewed later rather than included automatically.
- `MANUFACTURED RESIDENTIAL` has all zero `AreaBuildi` in Cobb. Including it would not change total square footage, but excluding it makes the built-square-footage definition clearer for the first pass.
- Multifamily categories should be included because the target is total residential square footage, not only single-family square footage.

Working first-pass SQL filter:

```sql
PECASResiTranche_MR IN (
  'SFR LESS THAN 1 ACRE',
  'SFR 1 ACRE OR MORE',
  'CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX',
  'MFR LESS THAN 3 FLOORS',
  'MFR 3 FLOORS OR MORE'
)
```

Working square-footage expression:

```sql
res_sqft = AreaBuildi
```

## Records Requiring Follow-Up Review

### Nonzero `VACANT RESIDENTIAL`

`VACANT RESIDENTIAL` has 11,095 records, of which 1,147 have nonzero `AreaBuildi`.

Calculation:

```text
11,095 total - 9,948 zero = 1,147 nonzero
```

These records should be reviewed to determine whether they are misclassified built residential parcels or whether the nonzero `AreaBuildi` reflects another structure type.

### Zero-square-foot built residential records

Built residential categories have some zero-square-foot records:

| Category | Zero `AreaBuildi` |
|---|---:|
| SFR LESS THAN 1 ACRE | 357 |
| CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX | 28 |
| SFR 1 ACRE OR MORE | 105 |
| MFR LESS THAN 3 FLOORS | 0 |
| MFR 3 FLOORS OR MORE | 3 |

These should be retained as zero for aggregation unless later QA suggests they are data errors requiring imputation or exclusion.

### Manufactured residential

`MANUFACTURED RESIDENTIAL` has 153 records, all with zero `AreaBuildi`.

This category may require a separate treatment if manufactured housing should contribute residential square footage. For the first pass, it is excluded from built residential square footage because there is no building area to aggregate.

## Largest `AreaBuildi` Records

Cobb layer: `RPD24_V2_13067`

Command:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT ARCID_MR, apn, PECASResiTranche_MR, LUTranche_MR, LUType_MR, AreaBuildi, ParcelAcreage_MR, YearBuilt FROM RPD24_V2_13067 ORDER BY AreaBuildi DESC LIMIT 20"
```

Result summary:

| Rank | ARCID_MR | APN | PECASResiTranche_MR | LUTranche_MR | LUType_MR | AreaBuildi | ParcelAcreage_MR | YearBuilt |
|---:|---|---|---|---|---|---:|---:|---:|
| 1 | 067.2025.249866 | 17081500400 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 3,929,999 | 32.3421868642 | 1995 |
| 2 | 067.2025.6128 | 19008100050 | NOT RESIDENTIAL | GOVERNMENT | GENERAL SERVICES | 2,025,540 | 1.29091082549 | 0 |
| 3 | 067.2025.222156 | 17098800040 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 1,779,364 | 8.68696792848 | 2000 |
| 4 | 067.2025.250098 | 17098600010 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 1,221,836 | 12.9106032828 | 1986 |
| 5 | 067.2025.231493 | 17097800340 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 1,116,209 | 5.13425748926 | 1989 |
| 6 | 067.2025.67707 | 17094700080 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 968,384 | 4.85863249953 | 1985 |
| 7 | 067.2025.184701 | 17094900100 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 967,515 | 7.18838516543 | 1988 |
| 8 | 067.2025.249972 | 17090900420 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 918,639 | 7.70469340075 | 1986 |
| 9 | 067.2025.110365 | 17091500160 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 905,236 | 6.90798714946 | 1984 |
| 10 | 067.2025.223679 | 17094700090 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 883,054 | 2.99297778033 | 1987 |
| 11 | 067.2025.242387 | 01022200030 | NOT RESIDENTIAL | GREENSPACE | GREENSPACE | 871,200 | 19.9553085518 | 0 |
| 12 | 067.2025.186609 | 17101300050 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 857,386 | 2.68894958734 | 2001 |
| 13 | 067.2025.149232 | 17094600060 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 789,925 | 3.98361009193 | 1999 |
| 14 | 067.2025.250130 | 18061200010 | NOT RESIDENTIAL | COMMERCIAL | RETAIL | 789,717 | 68.5192704207 | 2017 |
| 15 | 067.2025.184024 | 17094700050 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 787,804 | 5.31849482389 | 1981 |
| 16 | 067.2025.228943 | 17044300040 | NOT RESIDENTIAL | GOVERNMENT | EDUCATIONAL SERVICES | 783,753 | 32.626177323 | 1967 |
| 17 | 067.2025.172783 | 16107400010 | NOT RESIDENTIAL | COMMERCIAL | OFFICE | 780,203 | 10.380324644 | 1974 |
| 18 | 067.2025.7218 | 19125200020 | NOT RESIDENTIAL | GREENSPACE | GREENSPACE | 779,724 | 20.9641565584 | 2002 |
| 19 | 067.2025.112973 | 16050100080 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 733,450 | 4.21278999988 | 2018 |
| 20 | 067.2025.89041 | 18039600030 | NOT RESIDENTIAL | COMMERCIAL | RETAIL | 733,316 | 0.809042227806 | 1990 |

Interpretation:

- 19 of the top 20 largest `AreaBuildi` records are classified as `NOT RESIDENTIAL`.
- The largest overall record is a commercial office parcel with 3,929,999 square feet.
- The first-pass residential filter will remove most of the largest commercial/government/greenspace records.
- The only residential record in the top 20 is:
  - `ARCID_MR = 067.2025.112973`
  - `apn = 16050100080`
  - `PECASResiTranche_MR = MFR 3 FLOORS OR MORE`
  - `AreaBuildi = 733,450`
  - `ParcelAcreage_MR = 4.21278999988`
  - `YearBuilt = 2018`
- This large multifamily record appears plausible enough to retain for the first pass, but it should be included in outlier diagnostics.

QA conclusion:

- Extreme overall `AreaBuildi` values are mainly non-residential and should not contaminate the residential dependent variable if the `PECASResiTranche_MR` residential filter is applied.
- Residential extreme values should still be reviewed after aggregation to block groups.

## Largest Built-Residential `AreaBuildi` Records

Cobb layer: `RPD24_V2_13067`

Built-residential filter used:

```sql
PECASResiTranche_MR IN (
  'SFR LESS THAN 1 ACRE',
  'SFR 1 ACRE OR MORE',
  'CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX',
  'MFR LESS THAN 3 FLOORS',
  'MFR 3 FLOORS OR MORE'
)
```

Command:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT ARCID_MR, apn, PECASResiTranche_MR, LUTranche_MR, LUType_MR, AreaBuildi, ParcelAcreage_MR, YearBuilt FROM RPD24_V2_13067 WHERE PECASResiTranche_MR IN ('SFR LESS THAN 1 ACRE', 'SFR 1 ACRE OR MORE', 'CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX', 'MFR LESS THAN 3 FLOORS', 'MFR 3 FLOORS OR MORE') ORDER BY AreaBuildi DESC LIMIT 20"
```

Results:

| Rank | ARCID_MR | APN | PECASResiTranche_MR | LUTranche_MR | LUType_MR | AreaBuildi | ParcelAcreage_MR | YearBuilt |
|---:|---|---|---|---|---|---:|---:|---:|
| 1 | 067.2025.112973 | 16050100080 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 733,450 | 4.21278999988 | 2018 |
| 2 | 067.2025.176948 | 17074900610 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 726,155 | 13.8716114023 | 2006 |
| 3 | 067.2025.176400 | 17087000010 | MFR LESS THAN 3 FLOORS | RESIDENTIAL | MFR LESS THAN 3 FLOORS | 643,086 | 40.2453617735 | 1983 |
| 4 | 067.2025.175981 | 17085500060 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 612,660 | 46.6682272172 | 1986 |
| 5 | 067.2025.187597 | 17105700010 | MFR LESS THAN 3 FLOORS | RESIDENTIAL | MFR LESS THAN 3 FLOORS | 610,147 | 45.7284874098 | 1970 |
| 6 | 067.2025.175972 | 17088800010 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 600,598 | 51.0081055539 | 1985 |
| 7 | 067.2025.175742 | 17091700010 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 583,570 | 4.56923731922 | 2015 |
| 8 | 067.2025.183414 | 17079900030 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 582,685 | 37.9673309747 | 1971 |
| 9 | 067.2025.203285 | 16072700030 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 578,456 | 59.8561083024 | 1987 |
| 10 | 067.2025.175966 | 17084500020 | MFR LESS THAN 3 FLOORS | RESIDENTIAL | MFR LESS THAN 3 FLOORS | 560,836 | 60.8776133165 | 1979 |
| 11 | 067.2025.65881 | 17070800010 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 553,125 | 42.4689697894 | 1970 |
| 12 | 067.2025.186719 | 17101300010 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 550,144 | 4.70445684821 | 2014 |
| 13 | 067.2025.183415 | 17080300010 | MFR LESS THAN 3 FLOORS | RESIDENTIAL | MFR LESS THAN 3 FLOORS | 536,301 | 38.9047395814 | 1971 |
| 14 | 067.2025.149771 | 17097800480 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 509,000 | 4.36288319633 | 2013 |
| 15 | 067.2025.123459 | 16079200030 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 507,196 | 68.479934244 | 1988 |
| 16 | 067.2025.180956 | 17055300030 | MFR LESS THAN 3 FLOORS | RESIDENTIAL | MFR LESS THAN 3 FLOORS | 504,744 | 44.759889925 | 1971 |
| 17 | 067.2025.213805 | 20005400170 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 497,466 | 38.1845706336 | 2001 |
| 18 | 067.2025.171998 | 16113500090 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 494,076 | 33.3191403106 | 1975 |
| 19 | 067.2025.121118 | 16036000010 | MFR LESS THAN 3 FLOORS | RESIDENTIAL | MFR LESS THAN 3 FLOORS | 489,796 | 44.1867073289 | 1987 |
| 20 | 067.2025.222123 | 17091900030 | MFR 3 FLOORS OR MORE | RESIDENTIAL | MFR 3 FLOORS OR MORE | 486,095 | 5.15972368559 | 2018 |

Interpretation:

- The top 20 built-residential records are all multifamily:
  - `MFR 3 FLOORS OR MORE`
  - `MFR LESS THAN 3 FLOORS`
- This is expected for the largest residential building-area records.
- The largest built-residential record has `AreaBuildi = 733,450`.
- These records appear plausible enough for a first-pass aggregation, but should remain part of outlier diagnostics.
- No single-family parcel appears in the top 20 built-residential records, which is expected.

QA conclusion:

- The built-residential filter removes the largest non-residential building-area records.
- The remaining largest residential records are multifamily records and are consistent with the intended target variable.

## `apn` Uniqueness Check

Cobb layer: `RPD24_V2_13067`

Command:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT COUNT(*) AS n, COUNT(DISTINCT apn) AS distinct_apn, COUNT(*) - COUNT(DISTINCT apn) AS duplicate_apn_count FROM RPD24_V2_13067"
```

Results:

| Metric | Count |
|---|---:|
| Records | 264,126 |
| Distinct `apn` | 264,119 |
| Duplicate `apn` count | 7 |

Interpretation:

- `apn` is nearly unique but not perfectly unique.
- There are 7 more records than distinct APNs.
- `apn` should be treated as a parcel identifier, but not assumed to be a unique row key without duplicate handling.
- Duplicate APNs should be reviewed before aggregation if they have nonzero residential square footage.
- `ARCID_MR` may be a better internal row identifier if it is unique.

QA follow-up:

- List duplicate APNs and inspect whether they represent true duplicate records, multipart parcel records, condo/building records, or legitimate repeated assessment records.


## `ARCID_MR` Uniqueness Check

Cobb layer: `RPD24_V2_13067`

Command:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT COUNT(*) AS n, COUNT(DISTINCT ARCID_MR) AS distinct_arcid_mr, COUNT(*) - COUNT(DISTINCT ARCID_MR) AS duplicate_arcid_mr_count FROM RPD24_V2_13067"
```

Results:

| Metric | Count |
|---|---:|
| Records | 264,126 |
| Distinct `ARCID_MR` | 264,126 |
| Duplicate `ARCID_MR` count | 0 |

Interpretation:

- `ARCID_MR` is unique in the Cobb layer.
- `ARCID_MR` should be used as the row-level identifier for parcel/building processing and QA.
- `apn` remains useful as the county tax assessor parcel ID but is not perfectly unique.

Preliminary ID decision:

| Purpose | Field |
|---|---|
| Row-level unique identifier | `ARCID_MR` |
| County tax assessor parcel ID | `apn` |

## Duplicate `apn` Review

Cobb layer: `RPD24_V2_13067`

Command:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT apn, COUNT(*) AS n, SUM(AreaBuildi) AS sum_areabuildi FROM RPD24_V2_13067 GROUP BY apn HAVING COUNT(*) > 1 ORDER BY n DESC, apn"
```

Results:

| apn | Records | Sum `AreaBuildi` |
|---|---:|---:|
| TAXED IN COBB | 8 | 0 |

Interpretation:

- The apparent `apn` duplicates are all from a placeholder value: `TAXED IN COBB`.
- These 8 records have zero total `AreaBuildi`.
- Duplicate APNs do not appear to create a double-counting risk for residential building square footage.
- `ARCID_MR` remains the preferred unique row identifier.
- `apn` is still useful for traceability but should not be treated as guaranteed unique.

QA conclusion:

- No duplicate-APN issue appears to affect the dependent-variable aggregation for Cobb.

## First-Pass Built-Residential Filter Summary

Cobb layer: `RPD24_V2_13067`

Built-residential filter:

```sql
PECASResiTranche_MR IN (
  'SFR LESS THAN 1 ACRE',
  'SFR 1 ACRE OR MORE',
  'CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX',
  'MFR LESS THAN 3 FLOORS',
  'MFR 3 FLOORS OR MORE'
)
```

Command:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT COUNT(*) AS n, SUM(AreaBuildi) AS total_areabuildi, SUM(CASE WHEN AreaBuildi = 0 THEN 1 ELSE 0 END) AS zero_areabuildi FROM RPD24_V2_13067 WHERE PECASResiTranche_MR IN ('SFR LESS THAN 1 ACRE', 'SFR 1 ACRE OR MORE', 'CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX', 'MFR LESS THAN 3 FLOORS', 'MFR 3 FLOORS OR MORE')"
```

Results:

| Metric | Value |
|---|---:|
| Built-residential records | 236,007 |
| Total `AreaBuildi` | 593,866,703 |
| Zero `AreaBuildi` records | 493 |

Interpretation:

- The first-pass built-residential filter keeps most Cobb parcel records.
- The resulting total residential climate-controlled structure area is 593,866,703 sq ft.
- Only 493 records in the built-residential filter have zero `AreaBuildi`.
- These zero records can be retained as zero in aggregation, but should be counted in QA.
- This filtered dataset is suitable for Step 3 block-group assignment.

## Latitude/Longitude Availability for Built-Residential Records

Cobb layer: `RPD24_V2_13067`

Built-residential filter:

```sql
PECASResiTranche_MR IN (
  'SFR LESS THAN 1 ACRE',
  'SFR 1 ACRE OR MORE',
  'CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX',
  'MFR LESS THAN 3 FLOORS',
  'MFR 3 FLOORS OR MORE'
)
```

Command:

```bash
ogrinfo inputs/RegionalParcelDataSet2024/RPD24_V2.gdb RPD24_V2_13067 \
  -dialect SQLite \
  -sql "SELECT COUNT(*) AS n, SUM(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 ELSE 0 END) AS missing_lat_lon FROM RPD24_V2_13067 WHERE PECASResiTranche_MR IN ('SFR LESS THAN 1 ACRE', 'SFR 1 ACRE OR MORE', 'CONDO TOWNHOME DUPLEX TRIPLEX QUADPLEX', 'MFR LESS THAN 3 FLOORS', 'MFR 3 FLOORS OR MORE')"
```

Results:

| Metric | Value |
|---|---:|
| Built-residential records | 236,007 |
| Missing latitude or longitude | 0 |

Interpretation:

- All first-pass built-residential records have populated latitude and longitude fields.
- These coordinates can be used as a fallback for block-group assignment.
- The parcel layer also has polygon geometry, so Step 3 can choose between:
  - spatial join using parcel polygon centroid,
  - spatial join using provided latitude/longitude,
  - or comparison of both for QA.

Preliminary Step 3 assignment recommendation:

- Use the parcel polygon geometry/centroid as the primary method if geometry loading is reliable.
- Use provided `latitude`/`longitude` as a QA comparison or fallback.
- Since the layer CRS is EPSG:4326 and the coordinates are latitude/longitude, both should align with ACS/TIGER block group geometry in EPSG:4326.

## Working Step 2 Decisions
Unique row ID: ARCID_MR
Parcel ID: apn
Square-footage field: AreaBuildi
Square-footage meaning: Combined Square Footage of All Climate Controlled Structures
Residential filter: PECASResiTranche_MR built-residential categories
Geometry/assignment inputs: parcel polygon Shape plus latitude/longitude