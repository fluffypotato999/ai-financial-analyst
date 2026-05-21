# 5-Minute Demo Walkthrough

This guide walks through the five demo steps in order. Total time: ~5 minutes.
Practice once before any recruiter call.

---

## Before you start

Run the full pipeline to make sure all outputs exist:

```bash
make demo TICKER=PANW        # ~10 min first run (cmdstan download)
make demo TICKER=CRWD        # ~3 min once cmdstan is cached
```

Open three things in tabs/windows:
1. Tableau Public dashboard (or `dashboard/tableau_data/fact_financials.csv`)
2. `dashboard/PANW_model.xlsx`
3. `dashboard/PANW_exec_commentary_<DATE>.md`

---

## Step 1 — Tableau dashboard (90 seconds)

**What to show:** A real financial fact with a direct link to its source SEC filing.

1. Open the Tableau Public dashboard.
2. Navigate to the **Actual vs Forecast** sheet.
3. Hover over any revenue data point.
4. Point out the tooltip: `accession_no: 0001327567-26-000123` and the
   `filing_url` link.
5. Click the filing URL → shows the actual SEC EDGAR document.

**Talking point:**
> "Every data point in this dashboard traces back to a specific SEC EDGAR filing.
> This is the accession number — it uniquely identifies the filing that sourced
> this number. The Tableau tooltip links directly to the source document."

---

## Step 2 — Excel model (60 seconds)

**What to show:** BalanceCheck = $0, Sources sheet provenance, Base→Bull scenario toggle.

1. Open `PANW_model.xlsx`, navigate to **Balance_Sheet** sheet.
2. Show the BalanceCheck row — all cells should read `$0`.
   > "Assets equal liabilities plus equity by construction. Cash is the balancing item."
3. Navigate to the **Sources** sheet.
4. Pick any row — show the `accession_no` and `filing_url` columns.
   > "Every historical value in the model traces to its source filing."
5. Navigate to **Assumptions**, change `ActiveScenario` from `Base` to `Bull`.
6. Switch to Income_Statement — show revenue numbers update.
   > "One cell change, all 16 forecast quarters update across all three statements."

---

## Step 3 — Exec commentary (60 seconds)

**What to show:** Inline citations and the reasoning-vs-computation split.

1. Open `dashboard/PANW_exec_commentary_<DATE>.md`.
2. Point out an inline citation like:
   `Revenue of $1.2B [0001327567-26-000123] beat the prior-period forecast...`
3. Explain the architecture:
   > "All arithmetic happens in Python — variance vs. forecast, YoY growth,
   > gross margin delta. Claude receives pre-formatted strings like '$1.2B'
   > and '3.2%' and writes narrative only. A parse-then-compare guard validates
   > every numeric token in the output against the input JSON."
4. Run in dry-run mode to show the prompt:
   ```bash
   make commentary TICKER=PANW
   ```
   > "By default this prints the prompt without calling the API — a recruiter
   > without an API key still sees the full pipeline output."

---

## Step 4 — PANW → CRWD ticker switch (60 seconds)

**What to show:** The same code handles two fundamentally different company shapes.

**PANW (hardware-plus-subscription):**
- `has_physical_inventory = TRUE` → Inventory row in Excel → DIO driver applies
- Revenue_Disaggregation sheet present (Product vs. Subscription & Support)

**CRWD (pure-SaaS):**
- `has_physical_inventory = FALSE` → no Inventory row
- No Revenue_Disaggregation sheet

Demo:
1. Show `PANW_model.xlsx` → Balance_Sheet → InventoryNet row populated.
2. Show `PANW_model.xlsx` → Revenue_Disaggregation tab exists.
3. Run CRWD:
   ```bash
   make dashboard TICKER=CRWD
   ```
4. Open `dashboard/CRWD_model.xlsx` → Balance_Sheet → no InventoryNet row.
5. No Revenue_Disaggregation tab.

**Talking point:**
> "One config change — `TICKER=CRWD` — switches the entire pipeline. The
> `has_physical_inventory` flag in the warehouse drives the Excel model rendering.
> PANW has Strata appliances with real inventory; CrowdStrike is pure cloud."

**Important language note:**
> "Strata, Prisma, and Cortex are *product families*, not segments — PANW has
> one reportable segment under ASC 280, with two revenue categories: Product and
> Subscription & Support. Getting this wrong is a 30-second rejection."

---

## Step 5 — Eval harness (30 seconds)

**What to show:** Automated tests including the refusal-on-restatement scenario.

```bash
make eval
```

Expected output:
```
PASSED tests/eval/test_eval_pipeline.py::test_volume_driven_driver_detected
PASSED tests/eval/test_eval_pipeline.py::test_margin_driven_driver_detected
PASSED tests/eval/test_eval_pipeline.py::test_one_time_driver_detected
PASSED tests/eval/test_eval_pipeline.py::test_mix_driver_detected_as_not_computable
PASSED tests/eval/test_eval_pipeline.py::test_restatement_pipeline_refuses
...
18 passed
```

**Talking point:**
> "The eval harness tests five ground-truth scenarios. The key one is the restatement
> scenario — if a 10-K/A amendment is detected, the pipeline refuses to generate
> commentary rather than writing plausible text from potentially incorrect numbers.
> Force escalation on ambiguity is a Kepler Finance pattern."

---

## Common interview questions and prepared answers

**Q: How do you prevent the LLM from hallucinating numbers?**
A: Parse-then-compare guard: every dollar and percent token in the output is extracted
with a regex, parsed to a canonical float, and compared against every value in the
input JSON within ±0.5% tolerance. Forbidden word-forms (billion, bps), parens-negative
notation, and bare numbers are also caught. If any check fails, the script exits
non-zero and the output is discarded.

**Q: Why not use XGBoost / a deep learning model?**
A: Twenty quarterly observations. Any model with more parameters than data points
will overfit. LassoCV enforces sparsity — it automatically drops irrelevant macro
features and the resulting model is explainable to a CFO. Prophet and AutoARIMA add
structural time-series structure. The honest answer for n=20 is an ensemble
characterizing the *range*, not a single point estimate.

**Q: What does PANW report as segments?**
A: One operating and reportable segment (ASC 280). Revenue is disaggregated into
Product and Subscription & Support. Strata, Prisma, and Cortex are commercial product
families that span both categories — they're not segments.

**Q: Where does the NGS ARR forecast come from?**
A: It doesn't — NGS ARR is not structured XBRL and cannot be ingested from SEC EDGAR
automatically. It appears in press-release text and 10-Q narrative. This pipeline
forecasts consolidated GAAP revenue and explicitly discloses that gap. A production
system would integrate a data partner like Daloopa for unstructured KPI extraction.

**Q: How does this compare to Anthropic's official financial-services plugin pack?**
A: The official pack (`anthropics/financial-services`) covers similar ground with higher
polish and MCP servers for FactSet, S&P, LSEG, etc. This project is built from scratch
on free public data to demonstrate the underlying craft — XBRL synonym mapping,
BalanceCheck verification, provenance threading, hallucination prevention — and to be
fully reproducible without paid data subscriptions. For production work I would compose
the official plugins.
