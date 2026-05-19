"""Tests for src/build_warehouse.py.

Builds a DuckDB warehouse from fixture parquets and verifies all views,
including the has_physical_inventory and has_restatement flags.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import duckdb
import yaml

from src.build_warehouse import build, query_summary
from src.ingest_edgar import ingest

# ── Fixture helpers ────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    with (_FIXTURES / name).open() as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def _build_parquet(
    fixture_name: str,
    ticker: str,
    cik_int: int,
    tmp_path: Path,
) -> Path:
    """Ingest fixture → parquet in tmp_path; return parquet path."""
    facts = _load_fixture(fixture_name)
    config: dict[str, Any] = {
        "cik": str(cik_int).zfill(10),
        "cik_int": cik_int,
        "ticker": ticker,
        "name": f"Test {ticker}",
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
        ingest(ticker=ticker, years=10, facts_json=facts)

    return tmp_path / f"{ticker}_financials.parquet"


def _build_warehouse(
    fixture_name: str,
    ticker: str,
    cik_int: int,
    tmp_path: Path,
) -> Path:
    """Ingest fixture → parquet → DuckDB; return .duckdb path."""
    _build_parquet(fixture_name, ticker, cik_int, tmp_path)
    config_path = tmp_path / "company.yaml"

    with (
        patch("src.build_warehouse._CONFIG_PATH", config_path),
        patch("src.build_warehouse._PROCESSED_DIR", tmp_path),
    ):
        return build(ticker=ticker)


# ── has_physical_inventory ────────────────────────────────────────────────────


def test_has_physical_inventory_true_for_panw(tmp_path: Path) -> None:
    """PANW fixture has InventoryNet → has_physical_inventory must be TRUE."""
    db_path = _build_warehouse("panw_companyfacts.json", "PANW", 1327567, tmp_path)
    summary = query_summary(db_path)
    assert bool(summary["has_physical_inventory"]) is True


def test_has_physical_inventory_false_for_crwd(tmp_path: Path) -> None:
    """CRWD fixture has no Inventory → has_physical_inventory must be FALSE."""
    db_path = _build_warehouse("crwd_companyfacts.json", "CRWD", 1517396, tmp_path)
    summary = query_summary(db_path)
    assert bool(summary["has_physical_inventory"]) is False


def test_has_physical_inventory_false_for_snow(tmp_path: Path) -> None:
    """SNOW fixture has no Inventory → has_physical_inventory must be FALSE."""
    db_path = _build_warehouse("snow_companyfacts.json", "SNOW", 1640147, tmp_path)
    summary = query_summary(db_path)
    assert bool(summary["has_physical_inventory"]) is False


# ── has_restatement ───────────────────────────────────────────────────────────


def test_has_restatement_false_for_clean_data(tmp_path: Path) -> None:
    """PANW fixture has no /A filings → has_restatement must be FALSE."""
    db_path = _build_warehouse("panw_companyfacts.json", "PANW", 1327567, tmp_path)
    summary = query_summary(db_path)
    assert bool(summary["has_restatement"]) is False


def test_has_restatement_true_for_amendment_fixture(tmp_path: Path) -> None:
    """Restatement fixture has a 10-K/A that materially differs → TRUE."""
    db_path = _build_warehouse("restatement_companyfacts.json", "TEST", 9999999, tmp_path)
    summary = query_summary(db_path)
    assert bool(summary["has_restatement"]) is True


def test_restatement_details_populated(tmp_path: Path) -> None:
    """v_restatement_details should have rows for the amended period."""
    db_path = _build_warehouse("restatement_companyfacts.json", "TEST", 9999999, tmp_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute("SELECT * FROM v_restatement_details").fetchdf()
    finally:
        con.close()
    assert len(rows) > 0
    assert "amending_accession_no" in rows.columns
    # Amendment value is 1.05B vs original 1.0B → 5% diff (above 0.1% threshold)
    assert (rows["rel_diff"] > 0.001).all()


# ── View structure and content ────────────────────────────────────────────────


def test_income_statement_view_has_revenue(tmp_path: Path) -> None:
    """v_income_statement_quarterly must have non-null Revenue rows for PANW."""
    db_path = _build_warehouse("panw_companyfacts.json", "PANW", 1327567, tmp_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            "SELECT * FROM v_income_statement_quarterly WHERE Revenue IS NOT NULL"
        ).fetchdf()
    finally:
        con.close()
    assert len(df) > 0
    assert "revenue_accession" in df.columns
    assert "revenue_fact_id" in df.columns
    assert "revenue_filing_url" in df.columns


def test_income_statement_provenance_populated(tmp_path: Path) -> None:
    """Revenue provenance columns must be non-null wherever Revenue is not null."""
    db_path = _build_warehouse("panw_companyfacts.json", "PANW", 1327567, tmp_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            "SELECT revenue_fact_id, revenue_accession, revenue_filing_url "
            "FROM v_income_statement_quarterly WHERE Revenue IS NOT NULL"
        ).fetchdf()
    finally:
        con.close()
    for col in ("revenue_fact_id", "revenue_accession", "revenue_filing_url"):
        assert df[col].notna().all(), f"Null provenance in {col}"


def test_balance_sheet_inventory_null_for_saas(tmp_path: Path) -> None:
    """Pure-SaaS company (CRWD) should have all-NULL Inventory column in BS view."""
    db_path = _build_warehouse("crwd_companyfacts.json", "CRWD", 1517396, tmp_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            "SELECT Inventory FROM v_balance_sheet_quarterly WHERE Inventory IS NOT NULL"
        ).fetchdf()
    finally:
        con.close()
    assert len(df) == 0, "CRWD should have no Inventory rows"


def test_canonical_facts_deduplicates(tmp_path: Path) -> None:
    """v_canonical_facts should return exactly one row per (line_item, period_end, frame)."""
    db_path = _build_warehouse("panw_companyfacts.json", "PANW", 1327567, tmp_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        dup_check = con.execute(
            """
            SELECT line_item, period_end, period_type, frame, COUNT(*) AS cnt
            FROM v_canonical_facts
            GROUP BY line_item, period_end, period_type, frame
            HAVING cnt > 1
            """
        ).fetchdf()
    finally:
        con.close()
    assert len(dup_check) == 0, f"Duplicate canonical facts found:\n{dup_check}"


def test_key_metrics_quarterly_only(tmp_path: Path) -> None:
    """v_key_metrics must contain only quarterly rows."""
    db_path = _build_warehouse("panw_companyfacts.json", "PANW", 1327567, tmp_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute("SELECT DISTINCT period_type FROM v_key_metrics").fetchdf()
    finally:
        con.close()
    assert set(df["period_type"].tolist()) == {"Q"}


def test_data_quality_row_count(tmp_path: Path) -> None:
    """v_data_quality returns exactly one summary row."""
    db_path = _build_warehouse("panw_companyfacts.json", "PANW", 1327567, tmp_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute("SELECT * FROM v_data_quality").fetchdf()
    finally:
        con.close()
    assert len(df) == 1
