# ACS Residential Square Footage Regression Specification

## Objective

Estimate expected residential square feet per occupied household using ACS demographic and housing characteristics at the Census Block Group level.

The estimated coefficients will later be applied to individual households using known household attributes.

---

# Dependent Variable

## Residential square feet per occupied household

### Formula

```text
log(
    total_residential_sqft_bg
    /
    occupied_households_bg
)
```

### Inputs

| Variable | Source |
|---|---|
| `total_residential_sqft_bg` | Tax assessor parcel data aggregated to Census Block Group |
| `occupied_households_bg` | ACS Table B25003 |

---

## ACS Table for Occupied Households

### Table

`B25003` — Tenure

### Variable

| ACS Variable | Description |
|---|---|
| `B25003_001` | Occupied housing units |

This variable will be used as the denominator for residential square feet per household.

---

# Independent Variables

## 1. Expected Log Household Income

### ACS Table

`B19001` — Household Income in the Past 12 Months

### Purpose

Primary household demand-side predictor.

### Construction

Construct:

```text
E_log_income_bg
=
Σ(share_income_bin_i × log(income_midpoint_i))
```

### Notes

- Use income bin midpoints.
- For open-ended top bins, use a reasonable representative value.
- Use natural logarithms.

---

## 2. Expected Log Household Size

### ACS Table

`B11016` — Household Type by Household Size

### Purpose

Captures diminishing marginal space demand from additional household members.

### Construction

Construct:

```text
E_log_hhsize_bg
=
Σ(share_hhsize_j × log(hhsize_j))
```

### Notes

- Use household-size categories directly.
- For open-ended bins, use a reasonable representative size.
- Use natural logarithms.

---

## 3. Share of Households With Children

### ACS Table

`B11005` — Households by Presence of People Under 18 Years

### Purpose

Captures family-oriented housing demand.

### Construction

Construct:

```text
share_households_with_children_bg
=
households_with_children
/
all_households
```

---

# Dwelling Type / Structure Mix Variables

## ACS Table

`B25024` — Units in Structure

### Purpose

Captures local housing stock composition.

### Regression Treatment

Use structure-type shares as aggregate predictors.

Omit single detached housing as the reference category.

### Construction

Construct each variable as:

```text
share_category_bg
=
category_count
/
total_housing_units
```

using ACS counts from `B25024`.

These variables are proportions/shares, not raw counts.

### Variables

| Model Variable | ACS Category |
|---|---|
| `share_single_attached_bg` | 1-unit attached |
| `share_2_to_4_units_bg` | 2–4 units |
| `share_5_to_19_units_bg` | 5–19 units |
| `share_20plus_units_bg` | 20 or more units |
| `share_mobile_other_bg` | Mobile homes, boats, RVs, vans, etc. |

### Omitted Reference Category

| Omitted Category |
|---|
| Single detached |

### Notes

- The shares should approximately sum to 1.0 together with the omitted single-detached category.
- The estimated coefficients on these variables will later be interpreted as household-level dwelling-type effects relative to the omitted single-detached reference category.

---

# Housing Spaciousness Proxy

## Preferred Variable

### ACS Table

`B25041` — Bedrooms

### Purpose

Captures local housing-stock spaciousness.

### Construction

Construct:

```text
expected_bedrooms_bg
=
Σ(share_bedroom_bin_k × bedroom_midpoint_k)
```

### Notes

Expected bedrooms is preferred over median rooms because expectations behave more cleanly in regression models.

---

## Alternative Variable (Optional)

### ACS Table

`B25018` — Median Number of Rooms

### Variable

| Model Variable |
|---|
| `median_rooms_bg` |

Use only if expected bedrooms is inconvenient to construct.

---

# Initial Regression Specification

## Recommended Starting Model

```text
log(
    total_residential_sqft_bg
    /
    occupied_households_bg
)
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
```

Single detached housing is omitted as the reference dwelling type.

---

# Regression Weights

## Recommended Weight

Weight observations by:

```text
occupied_households_bg
```

using:

```text
B25003_001
```

### Rationale

- Larger block groups provide more stable ACS estimates.
- Small block groups exhibit higher sampling variance.
- Weighting approximates household-level estimation.

---

# Functional Form

## Recommended Form

Use a log-linear specification.

### Rationale

- Residential square footage is highly right-skewed.
- Housing consumption relationships are approximately multiplicative.
- Log form stabilizes variance.
- Household space demand likely exhibits diminishing marginal effects.

---

# Back-Transformation

When applying the model to individual households:

```text
predicted_sqft_h
=
exp(predicted_log_sqft_h) × smearing_factor
```

Estimate the smearing factor from regression residuals.

---

# Future Enhancements (Not Included Initially)

## Potential Additional Variables

| Variable | Candidate ACS Table |
|---|---|
| Median gross rent | B25064 |
| Median home value | B25077 |
| Gross rent as % of income | B25070 |
| Tenure | B25003 |
| Urban price controls | tract or metro fixed effects |

### Notes

Rent variables are not initially included because they may be unreliable in predominantly owner-occupied block groups.

These variables can be evaluated later as contextual market constraints.