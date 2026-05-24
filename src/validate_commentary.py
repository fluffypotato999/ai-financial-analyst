"""Standalone offline validator for commentary drafts.

Reuses ``run_hallucination_guard`` from :mod:`src.generate_commentary` so the
same guard logic that fires on live API output can be invoked against any
draft markdown — without rebuilding the DuckDB warehouse or calling the
Anthropic API.

Use cases:

* Iterate on a hand-edited prompt by validating drafts against a saved
  payload.
* Validate a Claude Code-generated commentary written from a dry-run
  payload, with no Anthropic API key on the local machine.
* CI smoke-checks of recorded fixtures.

Payload formats (auto-detected):

* **raw JSON** — the dict ``generate()`` passes as the user message.
* **full dry-run output** — the multi-line text emitted by
  ``python -m src.generate_commentary`` in dry-run mode (``SYSTEM:`` …
  ``USER:`` … with the JSON inside a ```json fenced block).

CLI::

    python -m src.validate_commentary --payload <path> --commentary <path>

Exit codes::

    0  guard passed
    1  guard violation (message printed to stderr)
    2  bad input (file missing, unparseable payload)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from src.generate_commentary import HallucinationError, run_hallucination_guard

logger = logging.getLogger(__name__)

_FENCED_JSON = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _load_payload(path: Path) -> dict[str, Any]:
    """Load a payload file as either raw JSON or full dry-run output.

    Args:
        path: Path to a payload file.

    Returns:
        The payload dict.

    Raises:
        ValueError: If the file cannot be parsed in either supported format.
    """
    text = path.read_text(encoding="utf-8")

    if text.lstrip().startswith("{"):
        return json.loads(text)  # type: ignore[no-any-return]

    if text.lstrip().startswith(("SYSTEM:", "=")):
        match = _FENCED_JSON.search(text)
        if match is None:
            raise ValueError(
                f"Payload file {path} looks like dry-run output but contains no "
                "```json fenced block."
            )
        return json.loads(match.group(1))  # type: ignore[no-any-return]

    raise ValueError(
        f"Payload file {path} is neither raw JSON (starts with '{{') nor dry-run "
        "output (starts with 'SYSTEM:' or '====')."
    )


def validate(payload_path: Path, commentary_path: Path) -> None:
    """Run the hallucination guard against a draft.

    Args:
        payload_path:    Path to the JSON payload (or full dry-run output).
        commentary_path: Path to the markdown commentary draft.

    Raises:
        HallucinationError: If the guard fires.
        FileNotFoundError:  If either file is missing.
        ValueError:         If the payload cannot be parsed.
    """
    if not payload_path.exists():
        raise FileNotFoundError(f"Payload not found: {payload_path}")
    if not commentary_path.exists():
        raise FileNotFoundError(f"Commentary not found: {commentary_path}")

    payload = _load_payload(payload_path)
    commentary = commentary_path.read_text(encoding="utf-8")
    run_hallucination_guard(commentary, payload)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns the process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    parser = argparse.ArgumentParser(
        prog="python -m src.validate_commentary",
        description=(
            "Run the hallucination guard against a commentary draft. " "No API key required."
        ),
    )
    parser.add_argument(
        "--payload",
        required=True,
        type=Path,
        help="Path to the payload (raw JSON, or full dry-run output text).",
    )
    parser.add_argument(
        "--commentary",
        required=True,
        type=Path,
        help="Path to the markdown commentary draft to validate.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help=(
            "Reserved: today the guard is already strict; the flag is accepted "
            "for forward-compat and to make CI invocations explicit."
        ),
    )
    args = parser.parse_args(argv)

    try:
        validate(args.payload, args.commentary)
    except HallucinationError as exc:
        print(f"HALLUCINATION GUARD FIRED:\n{exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print("Guard passed — all numeric tokens validated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
