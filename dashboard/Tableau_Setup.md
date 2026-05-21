# Tableau Setup — PANW Financial Model

> **⚠️ WARNING: Tableau Public publishes data WORLD-READABLE and Google-INDEXABLE.**
> **The SEC data here is already public, but if you ever extend this project to**
> **non-public sources, do NOT publish to Tableau Public.**

---

## 1. File Overview

The `/dashboard/tableau_data/` folder contains six files:

| File | Description |
|---|---|
| `fact_financials.csv` | Long-format quarterly actuals (all line items) with provenance |
| `fact_forecasts.csv` | Prophet + AutoARIMA + Lasso forecasts with 80%/95% CIs |
| `fact_consensus.csv` | Analyst consensus estimates (empty stub if not available) |
| `dim_date.csv` | Date dimension: fiscal year/quarter + calendar year/quarter |
| `dim_metric.csv` | Metric metadata: label, category, unit |
| `dim_filing.csv` | One row per `accession_no` with `filing_url`, `form_type`, `filed_date` |

---

## 2. Star Schema

Connect all tables in Tableau using these join keys:

```
fact_financials ──── dim_date    on  fact_financials.period_end = dim_date.date_key
fact_financials ──── dim_metric  on  fact_financials.line_item  = dim_metric.line_item
fact_financials ──── dim_filing  on  fact_financials.accession_no = dim_filing.accession_no
fact_forecasts  ──── dim_date    on  fact_forecasts.period_end  = dim_date.date_key
```

`dim_filing` is the **provenance dimension** — every mark on a Tableau viz can
carry a tooltip linking to the source SEC filing.

---

## 3. Connecting in Tableau Desktop / Tableau Public

1. Open Tableau Desktop or Tableau Public.
2. **Connect → Text File** → select `fact_financials.csv`.
3. Add remaining files via **Data Source** tab → drag each CSV to the canvas.
4. Create the joins as described above.
5. (Optional) Connect to the `.hyper` extract for faster performance.

---

## 4. Recommended Worksheets

### Sheet 1: Actual vs Forecast
- Rows: Revenue ($B)
- Columns: period_end (continuous)
- Marks: Line
- Dual axis: actuals (from `fact_financials`) + forecast bands (from `fact_forecasts`)
- **Add a "Source" tooltip** on every actual mark:
  ```
  Accession: <accession_no>
  Filed: <filed_date>
  Form: <form_type>
  ATTR([filing_url])  ← make this a URL action
  ```

### Sheet 2: Variance Drivers
- Once `v_variance_facts` is built (Prompt 7.5), export and add `fact_variance.csv`
- Bar chart: `revenue_variance_vs_forecast` per quarter
- Colour by driver type (volume / margin / mix / one-time)

### Sheet 3: Forecast Accuracy
- Line chart: MAE and MAPE per CV fold, grouped by model
- Reference line at 10% MAPE (guidance threshold)

### Sheet 4: Scenario Toggle
- Parameter: Base / Bull / Bear
- Filter `fact_forecasts` by model
- Show revenue forecast with CI bands

---

## 5. Sample Calculated Fields

Paste these into Tableau's **Calculated Field** editor:

```
// Revenue Variance %
([Revenue Actual] - [Revenue Forecast]) / ABS([Revenue Forecast])

// MAPE per fold
ABS(([Revenue Actual] - [Revenue Forecast]) / [Revenue Actual])

// YoY Revenue Growth
([Revenue] - LOOKUP([Revenue], -4)) / ABS(LOOKUP([Revenue], -4))
```

---

## 6. Provenance Tooltip Setup

On any worksheet showing actuals:
1. In the **Tooltip** editor, add:
   ```
   Source filing: <accession_no>
   Filed: <filed_date>  |  Form: <form_type>
   Click to open: <URL action>
   ```
2. Create a **URL Action**: Dashboard → Actions → URL
   - URL: `<filing_url>`
   - Run on: Hover or Click

This is what makes the model interview-defensible: every data point is one click
away from its source SEC filing.

---

## 7. Publishing to Tableau Public

1. Sign in to Tableau Public (free account).
2. File → Save to Tableau Public.
3. Copy the published URL and embed it in the project README.

**Reminder**: Once published, data is world-readable. The SEC EDGAR data used
here is already public, so this is appropriate. Do not publish if you add
any non-public data sources.
