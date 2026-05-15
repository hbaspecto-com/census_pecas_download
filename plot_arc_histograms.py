#!/usr/bin/env python3

"""
plot_arc_histograms.py

Creates histograms of regression results for all ARC county block groups
(17 counties; Coweta and 3 counties with no parcel layer excluded).

Reads the regression diagnostics CSV produced by:
  python acs_residential_sqft_regression.py --all

and produces histograms of:
  - Observed log sq ft per household
  - Observed sq ft per household
  - Predicted sq ft per household
  - Residuals (observed - predicted, log scale)
  - Absolute percent error
  - Block group count by county
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

OUTPUT_DIR = Path("outputs")
DIAGNOSTICS_FILE = OUTPUT_DIR / "acs_sqft_regression_diagnostics_arc_2024.csv"
PLOT_OUTPUT_FILE = OUTPUT_DIR / "histogram_arc_regression_results.png"

# ---------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------

df = pd.read_csv(DIAGNOSTICS_FILE)

print(f"Loaded {len(df):,} ARC block groups from {DIAGNOSTICS_FILE}")

# Derive county FIPS (3-digit) from GEOID (12-char: state2 + county3 + tract6 + bg1)
df["county_fips"] = df["geoid"].astype(str).str[2:5]

# County name lookup for the 17 included counties
COUNTY_NAMES = {
    "013": "Barrow",
    "015": "Bartow",
    "045": "Carroll",
    "057": "Cherokee",
    "063": "Clayton",
    "067": "Cobb",
    "085": "Dawson",
    "089": "DeKalb",
    "097": "Douglas",
    "113": "Fayette",
    "117": "Forsyth",
    "121": "Fulton",
    "135": "Gwinnett",
    "151": "Henry",
    "217": "Newton",
    "223": "Paulding",
    "247": "Rockdale",
}
df["county_name"] = df["county_fips"].map(COUNTY_NAMES).fillna(df["county_fips"])

# ---------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------

fig, axes = plt.subplots(2, 3, figsize=(18, 10))
fig.suptitle(
    f"ARC Region Block Group Regression Results — Histograms\n"
    f"({len(df):,} block groups, 17 counties)",
    fontsize=16,
)

def fmt_comma(x, pos):
    return f"{x:,.0f}"

# 1. Observed log sq ft per household
ax = axes[0, 0]
ax.hist(df["log_res_sqft_per_hh"], bins=30, color="steelblue", edgecolor="white")
ax.set_title("Observed Log Sq Ft per HH", fontsize=13)
ax.set_xlabel("Log(Sq Ft per Household)", fontsize=11)
ax.set_ylabel("Block Groups", fontsize=11)
ax.tick_params(axis="x", rotation=30)

# 2. Observed sq ft per household
sqft_bins = np.linspace(df["predicted_sqft_per_hh"].min(), df["predicted_sqft_per_hh"].max(), 31)
obs_sqft = np.exp(df["log_res_sqft_per_hh"])
obs_q1, obs_median, obs_q3 = np.percentile(obs_sqft, [25, 50, 75])
ax = axes[0, 1]
obs_counts, _, _ = ax.hist(obs_sqft, bins=sqft_bins, color="cornflowerblue", edgecolor="white")
ax.set_title("Observed Sq Ft per HH", fontsize=13)
ax.set_xlabel("Sq Ft per Household", fontsize=11)
ax.set_ylabel("Block Groups", fontsize=11)
ax.set_xlim(0, 6000)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(fmt_comma))
ax.tick_params(axis="x", rotation=30)
y_top = obs_counts.max()
for qval, qlabel in [(obs_q1, "Q1"), (obs_median, "Median"), (obs_q3, "Q3")]:
    ax.axvline(qval, color="navy", linewidth=1.2, linestyle="--")
    ax.text(qval, y_top * 0.97, f"{qlabel}\n{qval:,.0f}", ha="center", va="top", fontsize=13, color="black")

# 3. Predicted sq ft per household
pred_q1, pred_median, pred_q3 = np.percentile(df["predicted_sqft_per_hh"], [25, 50, 75])
ax = axes[0, 2]
pred_counts, _, _ = ax.hist(df["predicted_sqft_per_hh"], bins=sqft_bins, color="darkorange", edgecolor="white")
ax.set_title("Predicted Sq Ft per HH", fontsize=13)
ax.set_xlabel("Sq Ft per Household", fontsize=11)
ax.set_ylabel("Block Groups", fontsize=11)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(fmt_comma))
ax.tick_params(axis="x", rotation=30)
y_top = pred_counts.max()
for qval, qlabel in [(pred_q1, "Q1"), (pred_median, "Median"), (pred_q3, "Q3")]:
    ax.axvline(qval, color="saddlebrown", linewidth=1.2, linestyle="--")
    ax.text(qval, y_top * 0.97, f"{qlabel}\n{qval:,.0f}", ha="center", va="top", fontsize=13, color="black")

# 4. Residuals
ax = axes[1, 0]
ax.hist(df["residual"], bins=30, color="seagreen", edgecolor="white")
ax.set_title("Residuals (Observed − Predicted, log scale)", fontsize=13)
ax.set_xlabel("Residual (log sq ft per HH)", fontsize=11)
ax.set_ylabel("Block Groups", fontsize=11)
ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
ax.tick_params(axis="x", rotation=30)

# 5. Absolute percent error
ax = axes[1, 1]
ax.hist(df["abs_pct_error"], bins=30, color="firebrick", edgecolor="white")
ax.set_title("Absolute Percent Error", fontsize=13)
ax.set_xlabel("Absolute Percent Error", fontsize=11)
ax.set_ylabel("Block Groups", fontsize=11)

# 6. Block group count by county (horizontal bar chart)
ax = axes[1, 2]
county_counts = (
    df.groupby("county_name")
    .size()
    .reindex(sorted(COUNTY_NAMES.values()))
    .dropna()
    .astype(int)
)
county_counts.plot(kind="barh", ax=ax, color="slategray", edgecolor="white")
ax.set_title("Block Groups by County", fontsize=13)
ax.set_xlabel("Block Groups", fontsize=11)
ax.set_ylabel("", fontsize=11)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(fmt_comma))
for bar, val in zip(ax.patches, county_counts):
    ax.text(
        bar.get_width() + 1,
        bar.get_y() + bar.get_height() / 2,
        str(val),
        va="center",
        fontsize=10,
    )

plt.tight_layout()
plt.savefig(PLOT_OUTPUT_FILE, dpi=150)
print(f"Saved histogram plot to {PLOT_OUTPUT_FILE}")
plt.show()
