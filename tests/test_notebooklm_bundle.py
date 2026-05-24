"""Tests for src/build_notebooklm_bundle.py.

Covers reviewer-facing invariants:
  - The bundle's Excel summary reads the file actually produced by
    src/build_excel_model.py (filename agreement).
  - When a real PDF is downloaded for a filing, no sibling .txt placeholder
    is left on disk for NotebookLM to ingest.
  - Forecast summary renders a real markdown table with no "Missing
    optional dependency 'tabulate'" stub leaking through.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd

from src import build_excel_model, build_notebooklm_bundle
from src.build_notebooklm_bundle import (
    _build_excel_model_summary,
    _build_forecast_summary,
    _build_historical_financials,
    _download_sec_filing,
)


def test_excel_summary_filename_matches_excel_writer(tmp_path: Path) -> None:
    """The bundle reads the same filename build_excel_model writes.

    Read the canonical filename pattern from build_excel_model and assert
    _build_excel_model_summary recognizes a file at that path.
    """
    ticker = "TEST"
    expected_name = f"{ticker}_3Statement_Model.xlsx"
    excel_source = Path(build_excel_model.__file__).read_text(encoding="utf-8")
    assert expected_name.replace(ticker, "{resolved_ticker}") in excel_source.replace(
        '"', ""
    ) or expected_name.replace(ticker, "{ticker}") in excel_source.replace('"', ""), (
        "build_excel_model no longer writes the expected filename pattern; "
        "update build_notebooklm_bundle._build_excel_model_summary to match."
    )

    excel_path = tmp_path / expected_name
    excel_path.write_bytes(b"fake xlsx")
    with patch.object(build_notebooklm_bundle, "_DASHBOARD_DIR", tmp_path):
        summary = _build_excel_model_summary(ticker)

    assert "not found" not in summary, (
        "Bundle could not find the Excel file at the canonical path; " f"summary said:\n{summary}"
    )
    assert expected_name in summary


def test_download_sec_filing_removes_stale_txt_placeholder(tmp_path: Path) -> None:
    """A successful PDF download wipes any sibling .txt placeholder.

    NotebookLM ingests every file in the bundle; leaving a "Filing not in PDF
    format" placeholder next to the real PDF causes confusing citations.
    """
    pdf_dest = tmp_path / "02_latest_10K.pdf"
    stale_txt = pdf_dest.with_suffix(".txt")
    stale_txt.write_text("Filing 10-K not in PDF format.\n", encoding="utf-8")
    assert stale_txt.exists()

    fake_subs: dict[str, Any] = {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "accessionNumber": ["0000000000-00-000000"],
                "primaryDocument": ["something.pdf"],
            }
        }
    }

    class _FakeResp:
        status_code = 200
        content = b"%PDF-1.4 fake pdf bytes"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return fake_subs

    def _fake_get(url: str, **_kwargs: Any) -> _FakeResp:
        return _FakeResp()

    with patch("src.build_notebooklm_bundle.requests.get", _fake_get):
        ok = _download_sec_filing(1327567, "10-K", pdf_dest)

    assert ok is True
    assert pdf_dest.exists()
    assert not stale_txt.exists(), (
        f"Stale .txt placeholder was not removed; bundle would include "
        f"both {pdf_dest.name} and {stale_txt.name}."
    )


def test_sample_commentary_renamed_and_banner_added(tmp_path: Path) -> None:
    """When the source commentary is *_SAMPLE*, bundle file embeds SAMPLE in name + banner.

    Reviewer asked: don't ship a 07_exec_commentary.md whose accessions don't
    appear in 04_historical_financials.csv. Fix is to make sample-vs-live
    visible from filename and from a banner inside the file.
    """
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    sample_src = dashboard_dir / "TEST_exec_commentary_SAMPLE.md"
    sample_src.write_text(
        "# TEST Commentary (Sample)\nRevenue $1.0B [0000000000-00-000000]\n",
        encoding="utf-8",
    )
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "ticker: TEST\ncik: '0000000000'\ncik_int: 0\nname: Test Co\n"
        "fiscal_year_end_month: 12\nfiscal_year_end_day: 31\n",
        encoding="utf-8",
    )
    # Pre-create stale 07_exec_commentary.md to confirm cleanup.
    stale = bundle_dir / "07_exec_commentary.md"
    stale.write_text("# stale live commentary\n", encoding="utf-8")

    # Stub network + heavy build steps so we only exercise the commentary path.
    def _no_op(*_args: Any, **_kwargs: Any) -> bool:
        return True

    def _no_op_path(b_dir: Path) -> Path:
        out = b_dir / "_stub.html"
        out.write_text("stub", encoding="utf-8")
        return out

    with (
        patch.object(build_notebooklm_bundle, "_DASHBOARD_DIR", dashboard_dir),
        patch.object(build_notebooklm_bundle, "_BUNDLE_DIR", bundle_dir),
        patch.object(build_notebooklm_bundle, "_CONFIG_PATH", config_path),
        patch.object(build_notebooklm_bundle, "_PROCESSED_DIR", tmp_path),
        patch.object(build_notebooklm_bundle, "_MODELS_DIR", tmp_path),
        patch.object(build_notebooklm_bundle, "_download_sec_filing", _no_op),
        patch.object(build_notebooklm_bundle, "_generate_test_report", _no_op_path),
        patch.object(build_notebooklm_bundle, "_generate_eval_report", _no_op_path),
    ):
        written = build_notebooklm_bundle.build(ticker="TEST")

    sample_dest = bundle_dir / "07_exec_commentary_SAMPLE.md"
    live_dest = bundle_dir / "07_exec_commentary.md"
    assert sample_dest.exists(), "Sample commentary should be written under SAMPLE filename"
    assert not live_dest.exists(), "Stale 07_exec_commentary.md was not cleaned up"
    body = sample_dest.read_text(encoding="utf-8")
    assert "SAMPLE — illustrative only" in body, "Banner not injected into sample commentary"
    assert written["07_exec_commentary"] == sample_dest

    readme = (bundle_dir / "README_FOR_NOTEBOOKLM.md").read_text(encoding="utf-8")
    assert "07_exec_commentary_SAMPLE.md" in readme
    assert (
        "live commentary required" in readme.lower()
    ), "README should suppress the provenance demo prompt for sample commentary"


def test_historical_financials_uses_canonical_export(tmp_path: Path) -> None:
    """04_historical_financials.csv inherits the canonical export contract.

    The bundle's CSV-builder must reuse ``_export_fact_financials`` so that
    every (ticker, line_item, period_end) appears at most once and every row
    carries a non-null accession_no.  Previously the bundle ran its own SQL
    against ``v_canonical_facts`` and silently emitted YTD-vs-standalone
    duplicates plus rows with missing provenance.
    """
    import json

    import yaml

    from src.build_warehouse import build as build_warehouse
    from src.ingest_edgar import ingest

    fixtures_dir = Path(__file__).parent / "fixtures"
    with (fixtures_dir / "panw_companyfacts.json").open() as fh:
        facts = json.load(fh)

    config: dict[str, Any] = {
        "cik": "0001327567",
        "cik_int": 1327567,
        "ticker": "PANW",
        "name": "Test PANW",
        "fiscal_year_end_month": 7,
        "fiscal_year_end_day": 31,
        "sector_etf": "XLK",
    }
    config_path = tmp_path / "company.yaml"
    with config_path.open("w") as fh:
        yaml.dump(config, fh)

    with (
        patch("src.ingest_edgar._CONFIG_PATH", config_path),
        patch("src.ingest_edgar._DATA_DIR", tmp_path),
    ):
        ingest(ticker="PANW", years=10, facts_json=facts)

    with (
        patch("src.build_warehouse._CONFIG_PATH", config_path),
        patch("src.build_warehouse._PROCESSED_DIR", tmp_path),
    ):
        build_warehouse(ticker="PANW")

    with patch.object(build_notebooklm_bundle, "_PROCESSED_DIR", tmp_path):
        df = _build_historical_financials("PANW", fy_end_month=7)

    assert df is not None and len(df) > 0, "Bundle CSV should not be empty for PANW fixture"

    # Invariant 1: no duplicates per period_end (would have halved Tableau values).
    dupes = df.duplicated(subset=["period_end"]).sum()
    assert dupes == 0, f"Bundle CSV has {dupes} duplicate period_end rows"

    # Invariant 2: every row carries provenance.
    missing = df["accession_no"].isna().sum()
    assert missing == 0, f"Bundle CSV has {missing} rows with null accession_no"

    # Invariant 3: standalone (not YTD) values.  Q2 standalone Revenue for PANW
    # 2025-01-31 is ~2.257B; the YTD H1 cumulative is ~4.396B.  If the YTD row
    # ever wins the QUALIFY race in _export_fact_financials, this catches it.
    q2 = df[df["period_end"] == "2025-01-31"]
    if len(q2) > 0:
        rev = float(q2.iloc[0]["Revenue"])
        assert rev < 3.0e9, (
            f"Revenue for 2025-01-31 was {rev:.3e}; expected ~2.257B (Q2 standalone), "
            "not the ~4.396B YTD H1 cumulative."
        )

    # Invariant 4: distinct period_ends carry distinct (fiscal_year, fiscal_period)
    # pairs — comparative rows must not inherit the newer filing's labels.
    # ai-financial-analyst-bau regression catch.
    pair_to_periods = df.groupby(["fiscal_year", "fiscal_period"])["period_end"].nunique()
    assert (pair_to_periods <= 1).all(), (
        "Bundle CSV has fiscal labels duplicated across distinct period_ends:\n"
        f"{pair_to_periods[pair_to_periods > 1]}"
    )

    # Specific PANW check: 2025-01-31 must be FY2025 Q2 (July fiscal year),
    # NOT FY2026 Q2 inherited from the FY2026 Q2 10-Q's comparative row.
    if len(q2) > 0:
        assert (int(q2.iloc[0]["fiscal_year"]), q2.iloc[0]["fiscal_period"]) == (2025, "Q2"), (
            f"period_end=2025-01-31 should be (2025, Q2) for PANW July FY; got "
            f"({q2.iloc[0]['fiscal_year']}, {q2.iloc[0]['fiscal_period']})"
        )


def test_forecast_summary_renders_table_without_tabulate(tmp_path: Path) -> None:
    """05_forecast_summary.md must render a real table, not the tabulate stub.

    df.to_markdown() requires the optional ``tabulate`` package. When it
    isn't installed pandas inserts the literal string
        "Missing optional dependency 'tabulate'"
    into the output. NotebookLM ingests that as a citation source, which is
    worse than no table at all. We render the table ourselves.
    """
    parquet = tmp_path / "TEST_baseline_forecasts.parquet"
    pd.DataFrame(
        {
            "model": ["prophet", "autoarima"],
            "period_end": pd.to_datetime(["2026-04-30", "2026-07-31"]),
            "yhat": [1_000_000_000.0, 1_100_000_000.0],
            "yhat_lower_80": [9.0e8, 1.0e9],
            "yhat_upper_80": [1.1e9, 1.2e9],
        }
    ).to_parquet(parquet, index=False)

    with patch.object(build_notebooklm_bundle, "_MODELS_DIR", tmp_path):
        md = _build_forecast_summary("TEST")

    assert (
        "Missing optional dependency" not in md
    ), f"Forecast summary leaked the tabulate-missing stub:\n{md}"
    # The header row of the rendered table must be present.
    assert (
        "| model | period_end | yhat | yhat_lower_80 | yhat_upper_80 |" in md
    ), f"Expected markdown table header not found in output:\n{md}"
