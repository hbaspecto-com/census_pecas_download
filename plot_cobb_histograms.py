#!/usr/bin/env python3

"""
plot_cobb_histograms.py

Creates histograms of regression results for Cobb County block groups.

Reads the regression diagnostics CSV (Step 7 combined first-pass model) and
produces histograms of:
  - Observed log sq ft per household
  - Observed sq ft per household
  - Predicted sq ft per household
  - Residuals (observed - predicted, log scale)
  - Absolute percent error
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
DIAGNOSTICS_FILE = OUTPUT_DIR / "acs_sqft_regression_diagnostics_cobb_2024.csv"
PLOT_OUTPUT_FILE = OUTPUT_DIR / "histogram_cobb_regression_results.png"

# ---------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------

df = pd.read_csv(DIAGNOSTICS_FILE)

print(f"Loaded {len(df)} Cobb County block groups from {DIAGNOSTICS_FILE}")

# ---------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------

fig, axes = plt.subplots(2, 3, figsize=(16, 9))
fig.suptitle("Cobb County Block Group Regression Results — Histograms", fontsize=14)

# Helper to format x-axis tick labels with commas
def fmt_comma(x, pos):
    return f"{x:,.0f}"

# 1. Observed log sq ft per household
ax = axes[0, 0]
ax.hist(df["log_res_sqft_per_hh"], bins=20, color="steelblue", edgecolor="white")
ax.set_title("Observed Log Sq Ft per HH")
ax.set_xlabel("Log(Sq Ft per Household)")
ax.set_ylabel("Block Groups")
ax.tick_params(axis="x", rotation=30)

# 2. Observed sq ft per household
ax = axes[0, 1]
ax.hist(np.exp(df["log_res_sqft_per_hh"]), bins=20, color="cornflowerblue", edgecolor="white")
ax.set_title("Observed Sq Ft per HH")
ax.set_xlabel("Sq Ft per Household")
ax.set_ylabel("Block Groups")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(fmt_comma))
ax.tick_params(axis="x", rotation=30)

# 3. Predicted sq ft per household
ax = axes[0, 2]
ax.hist(df["predicted_sqft_per_hh"], bins=20, color="darkorange", edgecolor="white")
ax.set_title("Predicted Sq Ft per HH")
ax.set_xlabel("Sq Ft per Household")
ax.set_ylabel("Block Groups")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(fmt_comma))
ax.tick_params(axis="x", rotation=30)

# 4. Residuals
ax = axes[1, 0]
ax.hist(df["residual"], bins=20, color="seagreen", edgecolor="white")
ax.set_title("Residuals (Observed − Predicted)")
ax.set_xlabel("Residual (Sq Ft)")
ax.set_ylabel("Block Groups")
ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(fmt_comma))
ax.tick_params(axis="x", rotation=30)

# 5. Absolute percent error
ax = axes[1, 1]
ax.hist(df["abs_pct_error"], bins=20, color="firebrick", edgecolor="white")
ax.set_title("Absolute Percent Error")
ax.set_xlabel("Absolute Percent Error")
ax.set_ylabel("Block Groups")

# 6. Hide unused sixth panel
axes[1, 2].set_visible(False)

plt.tight_layout()
plt.savefig(PLOT_OUTPUT_FILE, dpi=150)
print(f"Saved histogram plot to {PLOT_OUTPUT_FILE}")
plt.show()
