# Continuous FAR Surface / Heat Map Concept for Parcel QA

## Purpose

We want to create a continuous spatial surface representing Floor Area Ratio (FAR) across the region using parcel-level building square footage and land square footage stored in PostGIS.

The primary purpose is **data quality assurance**, especially detecting cases where:

* every condominium unit parcel was incorrectly assigned the entire building square footage
* shared/common parcels are inconsistently represented
* land area is fragmented differently between developments
* unrealistic FAR values appear spatially isolated

Example:

* a 3-storey building with true FAR ≈ 1.2
* 100 condominium unit parcels each assigned the entire building square footage
* resulting parcel FAR ≈ 120

A continuous surface makes these anomalies visually obvious.

---

# Key Design Principle

We should **not** simply map parcel FAR directly.

Instead, we should compute a **local weighted FAR** over nearby parcels:

[
\text{Local FAR}(x)=
\frac{
\sum_i K(d_{ix}) \cdot \text{BuildingSqFt}*i
}{
\sum_i K(d*{ix}) \cdot \text{EffectiveLandSqFt}_i
}
]

Where:

* (K(d)) is a distance decay kernel
* nearby parcels contribute more heavily
* both numerator and denominator are spatially smoothed

This avoids problems where:

* one tower parcel includes all open space
* another tower splits green space into separate parcels
* roads and open space are represented inconsistently

The local neighborhood becomes the unit of analysis instead of the individual parcel.

---

# Why Include All Parcels?

It is important to include:

* residential parcels
* roads
* playgrounds
* green space parcels
* utility parcels
* open/common condominium parcels

because different developments subdivide land differently.

Example:

## Development A

* one parcel contains:

  * tower
  * landscaping
  * parking
  * sidewalks

## Development B

* separate parcels for:

  * tower footprint
  * green space
  * plaza
  * internal roads

A local smoothing approach makes these comparable.

---

# Why Large Parks and Farms Are a Problem

If we average over all nearby land equally, then:

* giant farms
* regional parks
* forests
* water bodies

can dilute the FAR surface excessively.

A downtown block beside a giant park could incorrectly appear low-density.

We therefore need an **effective land area cap** or weighting adjustment.

---

# Recommended Effective Land Area

Example:

```sql
effective_land_sqft =
CASE
  WHEN land_class IN ('regional_park','national_park','farm','forest')
    THEN LEAST(land_sqft, 200000)

  WHEN land_sqft > 500000
    THEN 200000

  ELSE land_sqft
END
```

This preserves local open-space effects while preventing giant parcels from dominating the denominator.

---

# Recommended Spatial Representation

## Preferred Approach: Regular Grid Surface

Rather than rasterizing immediately, create:

* square grid
* or hexagonal grid

Example sizes:

* 50m
* 100m
* 250m

Each cell stores:

* local weighted FAR
* supporting statistics
* anomaly indicators

Advantages:

* easier SQL workflows
* easier vector tile serving
* easier debugging
* easier aggregation
* easier styling in QGIS/MapLibre

---

# Example Grid Creation

```sql
CREATE MATERIALIZED VIEW far_grid_100m AS
WITH bounds AS (
  SELECT ST_Union(geom) AS geom
  FROM study_area
),
grid AS (
  SELECT
    row_number() over () AS grid_id,
    (g).geom
  FROM bounds,
       ST_SquareGrid(100, bounds.geom) AS g
)
SELECT *
FROM grid;
```

---

# Local FAR Calculation

## Recommended Formula

Use a ratio of weighted sums:

```sql
weighted_building_sqft /
weighted_effective_land_sqft
```

NOT:

```text
average(parcel_far)
```

because parcel FAR averages become unstable when parcels are subdivided differently.

---

# Example Kernel-Smoothed FAR SQL

```sql
CREATE MATERIALIZED VIEW far_surface_100m AS
SELECT
    g.grid_id,
    g.geom,

    SUM(
        p.building_sqft *
        EXP(-POWER(
            ST_Distance(
                ST_PointOnSurface(g.geom),
                p.pt
            ) / 400.0,
        2))
    )

    /

    NULLIF(

        SUM(
            p.effective_land_sqft *
            EXP(-POWER(
                ST_Distance(
                    ST_PointOnSurface(g.geom),
                    p.pt
                ) / 400.0,
            2))
        ),

    0)

    AS local_far

FROM far_grid_100m g

JOIN parcel_points p
  ON ST_DWithin(
        ST_PointOnSurface(g.geom),
        p.pt,
        1200
     )

GROUP BY g.grid_id, g.geom;
```

---

# Distance Parameters

Suggested values:

| Environment | Kernel Scale | Search Radius |
| ----------- | ------------ | ------------- |
| Dense Urban | 200–400m     | 800–1200m     |
| Suburban    | 400–800m     | 1200–2000m    |
| Rural       | 1000m+       | 3000m+        |

Could also vary adaptively based on local parcel size or density.

---

# Parcel Point Representation

Recommended preprocessing:

```sql
CREATE MATERIALIZED VIEW parcel_points AS
SELECT
    parcel_id,
    ST_PointOnSurface(geom) AS pt,
    building_sqft,
    land_sqft,
    effective_land_sqft
FROM parcels;
```

For very large parcels:

* subdivide geometries
* or sample multiple points

so contribution is spatially distributed appropriately.

---

# Condo Error Detection

The surface itself will reveal suspicious spikes, but dedicated diagnostics should also be built.

## Direct FAR Threshold

```sql
SELECT *
FROM parcels
WHERE building_sqft / NULLIF(land_sqft,0) > 20;
```

---

# Repeated Building Area Detection

This can detect condo duplication:

```sql
SELECT
    ROUND(building_sqft)::bigint AS repeated_sqft,
    COUNT(*) AS parcel_count,
    SUM(building_sqft) AS total_reported_sqft
FROM parcels
WHERE building_sqft > 10000
GROUP BY
    ROUND(building_sqft)::bigint,
    ST_SnapToGrid(ST_Centroid(geom), 100)
HAVING COUNT(*) >= 10;
```

This identifies many nearby parcels with identical large building square footage values.

---

# Visualization

## Recommended

Serve the grid as:

* vector tiles (preferred)
* or raster tiles

Vector tiles are likely easier and more flexible initially.

---

# Suggested Color Scale

Use logarithmic scaling because anomalies can be extreme.

Example conceptual breaks:

| FAR      | Meaning           |
| -------- | ----------------- |
| 0–0.05   | Rural/Open        |
| 0.05–0.3 | Low Density       |
| 0.3–1.5  | Urban Fabric      |
| 1.5–5    | Dense Urban       |
| 5–20     | Suspicious        |
| 20+      | Severe Data Error |

Suggested visualization value:

```text
log1p(local_far)
```

---

# Additional Useful Outputs

Each grid cell could also store:

* max parcel FAR nearby
* median parcel FAR
* parcel count
* residential-only FAR
* employment-only FAR
* variance / standard deviation
* anomaly score

These help distinguish:

* legitimate high density
* from data corruption

---

# Recommendation Summary

Recommended workflow:

1. preprocess parcel points
2. define effective land area
3. generate regular grid
4. compute kernel-smoothed weighted FAR
5. materialize results
6. expose via vector tiles
7. build companion anomaly layers

The key insight is:

> Use a spatially smoothed ratio of weighted building area to weighted effective land area, rather than parcel FAR itself.

That produces a stable continuous density surface suitable for:

* QA
* condo error detection
* visual diagnostics
* regional urban form analysis
* future model calibration support
