# Dashboard Screenshots

Add screenshots here after running the full pipeline and opening the Excel model.

## Recommended screenshots for the demo

| Filename                          | What to capture                                               |
|-----------------------------------|---------------------------------------------------------------|
| `01_balance_check_zero.png`       | Balance_Sheet tab — BalanceCheck row showing all $0 cells    |
| `02_sources_provenance.png`       | Sources tab — accession_no + filing_url columns visible      |
| `03_scenario_toggle.png`          | Assumptions tab — ActiveScenario dropdown (Base/Bull/Bear)   |
| `04_revenue_disaggregation.png`   | Revenue_Disaggregation tab — Product vs. S&S split           |
| `05_tableau_tooltip.png`          | Tableau Public — Actual vs Forecast with accession tooltip    |

## How to generate the pipeline outputs

```bash
make ingest TICKER=PANW
make warehouse TICKER=PANW
make dashboard TICKER=PANW       # creates PANW_3Statement_Model.xlsx
make commentary TICKER=PANW      # dry-run commentary
```

Screenshots should be 1920×1080 PNG, cropped to the relevant area.
