# Block Group Residential Square Feet Regression Plan

## Goal

Build a block-group-level regression dataset and model that explains variation in total residential building square footage using ACS household characteristics.

Initial scope:

- Geography: Cobb County, Georgia
- Unit of observation: Census block group
- Dependent variable: Total residential building square feet from parcel/building data
- Independent variables: ACS household counts by income and household size categories

Later scope:

- Expand from Cobb County to all 21 Atlanta Regional Commission counties
- Reuse the same workflow for all block groups in the 21 ARC counties
- Compare model performance and coefficients across the full ARC region

---

## Working Principle

The regression itself is not the hard part at first. The main task is creating a clean analytical table with exactly one row per block group.

The target modeling table should look like:

| GEOID | county | total_res_sqft | total_households | hh_size_1 | hh_size_2 | hh_income_low | hh_income_mid | ... |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 130670301001 | Cobb | 1250000 | 520 | 140 | 180 | 90 | 210 | ... |

The key join field is the 12-digit census block group GEOID:

```text
state FIPS + county FIPS + tract FIPS + block group
```

For Cobb County, GEOIDs begin with:

```text
13067
```

---

## Proposed Project Organization

Create a new script for the regression workflow so that the ACS download workflow stays separate.

Suggested new file:

```text
run_regression.py
```

Possible output folders:

```text
downloads/
  ACS and geometry downloads

inputs/
  parcel/building source files, if stored locally

outputs/
  regression_modeling_table_cobb_bg.csv
  regression_modeling_table_arc_bg.csv
  regression_results_cobb.txt
  regression_results_arc.txt
  regression_diagnostics_cobb.csv
```

Question:

- Should the parcel/building data live inside this repo, or will it be read from an external path/database?
    - Answer: Parcel data will live in this repo
---

# Step 1: Define the Initial Geography

## Objective

Start with Cobb County block groups only, then generalize to all ARC counties.

## Initial County

Cobb County:

```text
State FIPS: 13
County FIPS: 067
County name: Cobb
```

## Later Counties

Eventually run the same process for all 21 ARC counties.

## Tasks

- Confirm that all data sources use compatible census geography.
- Use block group GEOID as the primary geographic key.
- Filter ACS and parcel-derived data to Cobb County for the first pass.
- Keep the county filter configurable so the same workflow can later run for all ARC counties.

## Expected Output

A list or table of valid Cobb County block group GEOIDs.

Example columns:

| GEOID | state | county | tract | block_group |
|---|---|---|---|---|
| 130670301001 | 13 | 067 | 030100 | 1 |

## Questions to Answer

- Which census vintage should define block group boundaries: 2020, 2023 ACS geography, or something else?
    - Answer: Use 2024 ACS 5-year Detailed Tables and matching 2024 ACS/TIGER block group GEOIDs.
- Should the regression use only block groups that appear in both parcel data and ACS data?
    - Answer: Cobb County has quite complete parcel data, so shouldn't be a problem, but let's have a system to flag any
missing block groups from the parcel data or ACS data.
- For the later ARC-wide model, should we pool all counties into one model or also estimate county-specific models?
    - Answer: Start with a pooled ARC-wide model, then add county fixed effects. Use county-specific diagnostics to decide whether separate county models are needed.
---

# Step 2: Inventory the Parcel/Building Data

## Objective

Understand the parcel data well enough to compute total residential building square feet by block group.

## Needed Fields

At minimum, the parcel/building data needs:

- A unique parcel or building identifier
- Residential building square footage
- A geometry field, or latitude/longitude, or an existing block group GEOID
- A way to identify residential records

Possible useful fields:

- Land use code
- Property class
- Building type
- Number of residential units
- Year built
- Improvement square footage
- Living area square footage
- Building area square footage
- Parcel centroid
- Building footprint geometry

## Tasks

- Identify the source file or database table.
- Determine which square footage field should be used.
- Determine how residential records should be selected.
- Determine whether each record represents a parcel, building, unit, or assessment account.
- Check for missing, zero, or extreme square footage values.
- Decide how to handle duplicate records.

## Expected Output

A cleaned parcel/building table with the fields needed for aggregation.

Example columns:

| parcel_id | res_sqft | geometry_or_lon_lat | residential_flag |
|---|---:|---|---|
| P1 | 2400 | ... | true |
| P2 | 1800 | ... | true |

## Questions to Answer

- What is the parcel/building data format: CSV, shapefile, GeoPackage, PostGIS table, file geodatabase, or something else?
- What is the exact square footage field we should use?
- Does that field represent heated living area, total building area, improvement area, or something else?
- Which field identifies residential properties?
- Should multifamily/apartment records be included?
- Should mixed-use records be included? If yes, how should residential square footage be isolated?
- Are there known duplicate parcel/building records?
- Are vacant residential parcels included, and should they be excluded?
- Is the parcel data for Cobb only right now, or already available for all ARC counties?

---

# Step 3: Assign Parcel/Building Records to Block Groups

## Objective

Give every residential parcel/building record a block group GEOID.

## Possible Assignment Methods

Preferred order:

1. Use an existing reliable block group GEOID field if the parcel data already has one.
2. Spatial join using building footprint centroid.
3. Spatial join using parcel centroid.
4. Spatial overlay by area, if parcels cross block group boundaries and precision is important.

For a first working version, a centroid-based spatial join is usually acceptable.

## Tasks

- Load block group boundaries.
- Load parcel/building geometries or coordinates.
- Ensure both datasets use compatible coordinate reference systems.
- Assign each residential parcel/building to one block group.
- Flag records that do not match any block group.
- Restrict the first run to Cobb County.

## Expected Output

A parcel/building table with a block group GEOID.

Example columns:

| parcel_id | res_sqft | GEOID |
|---|---:|---|
| P1 | 2400 | 130670301001 |
| P2 | 1800 | 130670301001 |

## Questions to Answer

- Does the parcel data already include block group GEOIDs?
- If not, does it include geometry or only latitude/longitude?
- If parcels cross block group boundaries, is centroid assignment acceptable for the first version?
- Should unmatched parcels be dropped, manually reviewed, or reported separately?
- Should we assign by parcel centroid or building centroid if both are available?

---

# Step 4: Aggregate Residential Square Footage by Block Group

## Objective

Create the dependent variable for the regression.

## Dependent Variable

```text
total_res_sqft
```

Definition:

```text
Sum of residential building square feet for all residential parcel/building records assigned to a block group.
```

## Tasks

- Group residential parcel/building records by block group GEOID.
- Sum residential square footage.
- Count records per block group for QA.
- Optionally sum residential units if available.
- Check for block groups with zero parcel square footage.
- Check for extreme high values.

## Expected Output

A block-group-level dependent variable table.

Example columns:

| GEOID | total_res_sqft | residential_record_count | residential_unit_count |
|---|---:|---:|---:|
| 130670301001 | 1250000 | 430 | 520 |
| 130670302002 | 980000 | 310 | 390 |

## Questions to Answer

- Should block groups with no residential parcel records be kept with `total_res_sqft = 0`, or excluded?
- Should records with missing square footage be excluded or treated as zero?
- Should extreme square footage values be capped, flagged, or left unchanged?
- Do we need separate dependent variables for single-family, multifamily, and total residential square footage?

---

# Step 5: Prepare ACS Household Predictors

## Objective

Create block-group-level independent variables from ACS household data.

## First-Pass Predictors

Start simple before trying the full income-by-size category structure.

Recommended first-pass ACS predictors:

- Total households
- Household size categories
- Household income distribution categories

Example variables:

| Variable | Meaning |
|---|---|
| total_households | Total households |
| hh_size_1 | 1-person households |
| hh_size_2 | 2-person households |
| hh_size_3 | 3-person households |
| hh_size_4 | 4-person households |
| hh_size_5 | 5-person households |
| hh_size_6plus | 6-or-more-person households |
| hh_income_lt_25k | Households below $25k |
| hh_income_25k_50k | Households $25k-$49,999 |
| hh_income_50k_100k | Households $50k-$99,999 |
| hh_income_100k_plus | Households $100k+ |

## Later Predictors

Move toward ARC-style income-by-size categories if feasible.

Target concept:

```text
4 income categories x 6 household size categories = 24 household type variables
```

Possible example structure:

| Income category | Household size category |
|---|---|
| Income group 1 | 1 person |
| Income group 1 | 2 persons |
| Income group 1 | 3 persons |
| Income group 1 | 4 persons |
| Income group 1 | 5 persons |
| Income group 1 | 6+ persons |
| Income group 2 | 1 person |
| ... | ... |

## Tasks

- Identify ACS tables available at block group level.
- Select variables needed for total households, household size, and income categories.
- Convert ACS estimate columns to numeric.
- Rename Census variable codes to readable names.
- Combine ACS bins into broader categories where useful.
- Preserve margins of error if we want to evaluate ACS uncertainty later.
- Filter to Cobb County for the first run.

## Expected Output

A block-group-level ACS predictor table.

Example columns:

| GEOID | total_households | hh_size_1 | hh_size_2 | hh_income_lt_25k | hh_income_25k_50k | ... |
|---|---:|---:|---:|---:|---:|---:|
| 130670301001 | 520 | 140 | 180 | 90 | 130 | ... |

## Questions to Answer

- What are the exact ARC 4 income categories?
- What are the exact ARC 6 household size categories?
- Is it acceptable to start with ACS-native bins and later recode to ARC categories?
- Do we need estimates only, or should margins of error be included in outputs?
- Should ACS household counts be rounded, left as estimates, or converted to integers?
- Which ACS year should be used: 2023 ACS 5-year, or a different year matching the parcel data?
- If income-by-size is not directly available at block group level, should we approximate it, use tract-level data, or start with separate income and size distributions?

---

# Step 6: Join Parcel-Derived Dependent Variable to ACS Predictors

## Objective

Create one modeling table with one row per block group.

## Join Key

```text
GEOID
```

## Tasks

- Join the block-group square footage table to the ACS predictor table.
- Keep only Cobb County for the initial run.
- Confirm that GEOID is a string, not a number.
- Verify that leading zeros are preserved.
- Check row counts before and after the join.
- Identify block groups missing parcel data.
- Identify block groups missing ACS data.
- Decide how missing values should be handled.

## Expected Output

A modeling table.

Example columns:

| GEOID | county | total_res_sqft | total_households | hh_size_1 | hh_size_2 | hh_income_lt_25k | ... |
|---|---|---:|---:|---:|---:|---:|---:|
| 130670301001 | Cobb | 1250000 | 520 | 140 | 180 | 90 | ... |

Suggested output file:

```text
outputs/regression_modeling_table_cobb_bg.csv
```

## Questions to Answer

- Should the modeling table include all ACS block groups, even if parcel square footage is missing?
- Should missing parcel square footage be interpreted as zero or unknown?
- Should missing ACS values cause the block group to be dropped?
- Do we need a separate QA report listing dropped or unmatched block groups?

---

# Step 7: Run Initial Sanity-Check Regressions

## Objective

Verify that the dataset behaves as expected before building a detailed model.

## Recommended First Models

### Model 1: Total Households Only

```text
total_res_sqft ~ total_households
```

Purpose:

- Basic sanity check.
- We expect a strong positive relationship.

### Model 2: Household Size Counts

```text
total_res_sqft ~ hh_size_1 + hh_size_2 + hh_size_3 + hh_size_4 + hh_size_5 + hh_size_6plus
```

Purpose:

- Estimate how total residential square footage varies with household size mix.

Important modeling choice:

- If all household-size categories sum to total households, use either:
  - all categories with no intercept, or
  - omit one category and keep an intercept.

### Model 3: Income Category Counts

```text
total_res_sqft ~ hh_income_lt_25k + hh_income_25k_50k + hh_income_50k_100k + hh_income_100k_plus
```

Purpose:

- Estimate how total residential square footage varies with income composition.

### Model 4: Combined First-Pass Model

```text
total_res_sqft ~ household_size_categories + income_categories
```

Purpose:

- Test whether household size and income distribution jointly explain block-group square footage.

## Tasks

- Run ordinary least squares regression.
- Save coefficient estimates.
- Save model summary statistics.
- Save predicted values and residuals by block group.
- Plot or tabulate observed vs. predicted values.
- Identify outlier block groups.

## Expected Outputs

```text
outputs/regression_results_cobb.txt
outputs/regression_diagnostics_cobb.csv
```

Diagnostics table example:

| GEOID | total_res_sqft | predicted_res_sqft | residual | abs_pct_error |
|---|---:|---:|---:|---:|
| 130670301001 | 1250000 | 1180000 | 70000 | 0.056 |

## Questions to Answer

- Should the first model include an intercept?
- Should the dependent variable be total square feet or square feet per household?
- Should we use raw counts, shares, or both?
- Should we weight the regression by number of households?
- What level of model accuracy is considered acceptable for the intended use?

---

# Step 8: Choose the Main Modeling Specification

## Objective

Decide what model best matches the intended interpretation.

## Candidate Specifications

### Option A: Count Model with No Intercept

```text
total_res_sqft ~ household_category_counts - 1
```

Interpretation:

- Each coefficient approximates square feet associated with one household in that category.

Pros:

- Intuitive for translating household forecasts into square footage demand.
- Works naturally when categories sum to total households.

Cons:

- Can be sensitive to category noise.
- Assumes each category contributes additively to total square footage.

### Option B: Count Model with Omitted Reference Category

```text
total_res_sqft ~ category_1 + category_2 + ... + category_k_minus_1
```

Interpretation:

- Coefficients are relative to the omitted category.

Pros:

- Standard regression setup.
- Avoids perfect multicollinearity.

Cons:

- Less directly interpretable as square feet per household type.

### Option C: Total Households Plus Composition Shares

```text
total_res_sqft ~ total_households + household_category_shares
```

Interpretation:

- Separates scale from composition.
- Total households captures size of the block group.
- Shares capture household mix.

Pros:

- Often statistically stable.
- Useful for understanding whether composition matters beyond total households.

Cons:

- Less direct for forecasting square footage from household category counts.

### Option D: Square Feet per Household Model

```text
sqft_per_household ~ household_category_shares
```

Interpretation:

- Models average residential square feet per household as a function of household mix.

Pros:

- Focuses on intensity rather than total scale.
- Easier to compare dense and less-dense block groups.

Cons:

- Requires careful handling of block groups with zero or very low household counts.

## Questions to Answer

- Is the primary goal explanation, prediction, or converting household forecasts into square footage demand?
- Do we want coefficients that can be interpreted as square feet per household category?
- Should the final model predict total square feet or square feet per household?
- Should the same coefficients be applied across all ARC counties?
- Should the model include county fixed effects when expanded to all counties?

---

# Step 9: Add Quality-Control Checks

## Objective

Catch data problems before trusting the regression.

## Checks

### Geography Checks

- Number of block groups in ACS data
- Number of block groups in parcel aggregation
- Number of block groups in joined modeling table
- GEOID format is 12 characters
- All Cobb GEOIDs start with `13067`

### Parcel Checks

- Total residential square feet by county
- Number of residential records by county
- Missing square footage count
- Zero square footage count
- Extreme square footage records
- Unmatched parcel/building records

### ACS Checks

- Missing ACS values
- Negative ACS values, if any
- Household size category totals compared with total households
- Income category totals compared with total households
- Block groups with very small household counts
- ACS margins of error, if retained

### Regression Checks

- R-squared and adjusted R-squared
- Residual distribution
- Largest positive and negative residuals
- Observed vs. predicted correlation
- Multicollinearity warnings
- Coefficients with unexpected signs
- Sensitivity to dropping outliers

## Expected Outputs

```text
outputs/qa_cobb_bg.txt
outputs/regression_diagnostics_cobb.csv
```

## Questions to Answer

- Should QA failures stop the script, or only print warnings?
- What thresholds should define an outlier?
- Should block groups with very low household counts be excluded?
- Should we create maps of residuals later?

---

# Step 10: Expand from Cobb County to All ARC Counties

## Objective

Generalize the workflow after it works for Cobb.

## Tasks

- Replace the single-county Cobb filter with a configurable county list.
- Run parcel processing for all available ARC county parcel datasets.
- Ensure consistent residential filters and square footage fields across counties.
- Create one ARC-wide modeling table.
- Add county name and county FIPS fields.
- Run the same QA checks county by county.
- Estimate ARC-wide regression models.
- Optionally estimate county-specific regressions for comparison.

## Expected Output

```text
outputs/regression_modeling_table_arc_bg.csv
outputs/regression_results_arc.txt
outputs/regression_diagnostics_arc.csv
outputs/qa_arc_bg.txt
```

## Questions to Answer

- Are parcel data fields standardized across all 21 counties?
- If not, do we need county-specific field mappings?
- Are all counties available for the same year?
- Should counties with incomplete parcel data be excluded?
- Should the ARC-wide model include county fixed effects?
- Should coefficients be allowed to vary by county or subregion?
- Do we want one final regional model or separate county models?

---

# Step 11: Move Toward ARC 4x6 Household Categories

## Objective

Replace or supplement the first-pass ACS predictors with ARC-style household income-by-size categories.

## Target Structure

Create up to 24 household category variables:

```text
4 income groups x 6 household size groups
```

Example naming convention:

```text
hh_inc1_size1
hh_inc1_size2
hh_inc1_size3
hh_inc1_size4
hh_inc1_size5
hh_inc1_size6plus
hh_inc2_size1
...
hh_inc4_size6plus
```

## Tasks

- Define the exact ARC income bins.
- Define the exact ARC household size bins.
- Identify whether ACS provides the needed cross-tabulation at block group level.
- If direct ACS data are unavailable, choose an approximation strategy.
- Rebuild the modeling table with the 4x6 variables.
- Re-run model diagnostics.
- Compare performance against simpler ACS-native models.

## Possible Approximation Strategies

If a direct income-by-size cross-tab is unavailable or unreliable at block group level:

1. Use separate income and size distributions only.
2. Estimate income-by-size counts using tract-level relationships and block-group marginal totals.
3. Use iterative proportional fitting if both marginal distributions are available.
4. Use a simpler model for the first deliverable and defer full 4x6 categories.

## Questions to Answer

- What are the official ARC 4 income categories?
- What are the official ARC 6 household size categories?
- Does ARC already provide household forecasts or base-year household counts in the 4x6 structure?
- If ACS does not directly support 4x6 at block group level, is approximation acceptable?
- Should the first production model use ACS-native categories or ARC 4x6 categories?

---

# Step 12: Document Final Decisions

## Objective

Keep a record of modeling choices so results are reproducible and interpretable.

## Decisions to Document

- Parcel source and date
- ACS year and release
- Geography vintage
- County list
- Residential parcel filter
- Square footage field
- Spatial assignment method
- ACS tables and variables used
- Category recoding rules
- Missing-data rules
- Regression specification
- Whether model includes intercept
- Whether model uses weights
- Outlier handling
- Final output filenames

## Suggested Documentation File

```text
REGRESSION_PLAN.md
```

Or, after implementation:

```text
REGRESSION_METHODS.md
```

## Questions to Answer

- Should this plan live in the repo as `REGRESSION_PLAN.md`?
- Should final methodology be documented separately once decisions are finalized?
- Who is the intended audience for the final methods documentation: internal project team, ARC staff, public technical users, or all of the above?

---

# Initial Implementation Checklist

Use this checklist for the first Cobb County version.

## Inputs

- [ ] Confirm parcel/building data source
- [ ] Confirm residential square footage field
- [ ] Confirm residential land-use/property filter
- [ ] Confirm block group boundary source
- [ ] Confirm ACS year
- [ ] Confirm first-pass ACS variables

## Data Preparation

- [ ] Load parcel/building data
- [ ] Filter to residential records
- [ ] Assign records to block groups
- [ ] Aggregate residential square footage by block group
- [ ] Load ACS household predictors
- [ ] Filter ACS data to Cobb County
- [ ] Join parcel totals to ACS predictors
- [ ] Save Cobb modeling table

## QA

- [ ] Check GEOID formatting
- [ ] Check row counts
- [ ] Check unmatched parcels/buildings
- [ ] Check missing square footage
- [ ] Check missing ACS values
- [ ] Check block groups with zero or tiny household counts
- [ ] Check extreme dependent-variable values

## Regression

- [ ] Run total-households-only model
- [ ] Run household-size model
- [ ] Run income-category model
- [ ] Run combined first-pass model
- [ ] Save model summaries
- [ ] Save predictions and residuals
- [ ] Review largest residuals

## Expansion

- [ ] Generalize county filtering
- [ ] Confirm parcel data availability for all 21 counties
- [ ] Add county-level QA summaries
- [ ] Run ARC-wide model
- [ ] Compare Cobb-only and ARC-wide results