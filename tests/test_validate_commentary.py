"""Tests for src/validate_commentary.py — the offline guard CLI.

These pin three contracts:

  1. The CLI exits 0 on a clean draft, 1 on a guard violation, 2 on bad
     input.
  2. Both payload formats — raw JSON and full dry-run output — are parsed.
  3. The CLI calls ``run_hallucination_guard`` directly (no duplicate
     parse-then-compare logic), so guard tests in ``test_commentary_guard``
     cover validate_commentary too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.validate_commentary import _load_payload, main, validate

# Match _PAYLOAD_1_2B in tests/test_commentary_guard.py.
_VALID_ACCESSION = "0001327567-26-000123"
_PAYLOAD = {
    "ticker": "TEST",
    "fiscal_year": 2026,
    "fiscal_period": "Q1",
    "revenue": {
        "value": "$1.2B",
        "fact_id": "abc123",
        "accession": _VALID_ACCESSION,
        "filing_url": "https://www.sec.gov/Archives/edgar/data/1327567/000132756726000123/",
    },
    "revenue_yoy_growth_pct": {"value": "12.3%"},
    "gross_margin_pct_actual": {"value": "8.0%"},
    "operating_margin_pct_actual": {"value": "5.5%"},
}

_CLEAN_COMMENTARY = (
    f"Revenue of $1.2B [{_VALID_ACCESSION}] was in line with expectations. "
    f"YoY growth was 12.3%."
)

_FABRICATED_COMMENTARY = f"Revenue of $1.5B [{_VALID_ACCESSION}] beat the plan."

_MISSING_CITATION_COMMENTARY = "Revenue of $1.2B was solid."


def _write_payload_json(tmp_path: Path) -> Path:
    """Write the payload as raw JSON (format A)."""
    p = tmp_path / "payload.json"
    p.write_text(json.dumps(_PAYLOAD), encoding="utf-8")
    return p


def _write_payload_dry_run(tmp_path: Path) -> Path:
    """Write the payload as full dry-run output (format B)."""
    p = tmp_path / "dry_run.txt"
    body = (
        "=" * 72 + "\n"
        "DRY-RUN MODE — Prompt that would be sent to Claude:\n" + "=" * 72 + "\n\n"
        "SYSTEM:\nYou are a CFO writing variance commentary.\n\n"
        "USER:\nHere is the pre-computed variance data for this quarter.\n\n"
        f"```json\n{json.dumps(_PAYLOAD, indent=2)}\n```\n\n" + "=" * 72 + "\n"
        "(Pass --live to call the Anthropic API)\n"
    )
    p.write_text(body, encoding="utf-8")
    return p


def _write_commentary(tmp_path: Path, body: str, name: str = "draft.md") -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_load_payload_raw_json(tmp_path: Path) -> None:
    """Raw-JSON payloads are loaded as a dict equal to the original."""
    p = _write_payload_json(tmp_path)
    assert _load_payload(p) == _PAYLOAD


def test_load_payload_dry_run_format(tmp_path: Path) -> None:
    """Dry-run output is parsed by extracting the fenced ```json block."""
    p = _write_payload_dry_run(tmp_path)
    assert _load_payload(p) == _PAYLOAD


def test_load_payload_rejects_unrecognized_format(tmp_path: Path) -> None:
    """Random text that's neither JSON nor dry-run output → ValueError."""
    p = tmp_path / "garbage.txt"
    p.write_text("not a payload at all\n", encoding="utf-8")
    with pytest.raises(ValueError, match="neither raw JSON"):
        _load_payload(p)


def test_validate_passes_on_clean_draft(tmp_path: Path) -> None:
    """A clean commentary against the matching payload → no exception."""
    payload = _write_payload_json(tmp_path)
    commentary = _write_commentary(tmp_path, _CLEAN_COMMENTARY)
    validate(payload, commentary)


def test_cli_exit_zero_on_clean_draft(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """python -m src.validate_commentary on a clean draft → exit 0."""
    payload = _write_payload_json(tmp_path)
    commentary = _write_commentary(tmp_path, _CLEAN_COMMENTARY)
    rc = main(["--payload", str(payload), "--commentary", str(commentary)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Guard passed" in out


def test_cli_exit_one_on_fabricated_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A draft with a fabricated $1.5B (input is $1.2B) → exit 1, error names the bad token."""
    payload = _write_payload_json(tmp_path)
    commentary = _write_commentary(tmp_path, _FABRICATED_COMMENTARY)
    rc = main(["--payload", str(payload), "--commentary", str(commentary)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "HALLUCINATION GUARD FIRED" in err
    assert "$1.5B" in err


def test_cli_exit_one_on_missing_citation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dollar token with no [accession_no] within 50 chars → exit 1."""
    payload = _write_payload_json(tmp_path)
    commentary = _write_commentary(tmp_path, _MISSING_CITATION_COMMENTARY)
    rc = main(["--payload", str(payload), "--commentary", str(commentary)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no citation" in err


def test_cli_accepts_dry_run_payload_format(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI parses full dry-run output (format B) the same as raw JSON (format A)."""
    payload = _write_payload_dry_run(tmp_path)
    commentary = _write_commentary(tmp_path, _CLEAN_COMMENTARY)
    rc = main(["--payload", str(payload), "--commentary", str(commentary)])
    assert rc == 0


def test_cli_exit_two_on_missing_payload(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nonexistent payload path → exit 2 (input error, distinct from guard fail)."""
    commentary = _write_commentary(tmp_path, _CLEAN_COMMENTARY)
    rc = main(["--payload", str(tmp_path / "missing.json"), "--commentary", str(commentary)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Payload not found" in err


def test_cli_help_lists_required_flags(capsys: pytest.CaptureFixture[str]) -> None:
    """--help mentions --payload, --commentary, --strict (acceptance criterion)."""
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--payload" in out
    assert "--commentary" in out
    assert "--strict" in out
