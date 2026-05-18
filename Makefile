TICKER  ?= PANW
PYTHON  := .venv/bin/python
PIP     := .venv/bin/pip

.PHONY: setup ingest warehouse model forecast dashboard commentary \
        notebooklm test eval lint typecheck qa demo clean

# ── Environment ───────────────────────────────────────────────────────────────
setup:
	python3.11 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "NOTE: First 'make forecast' triggers cmdstan download (~200 MB, ~5 min)."
	@echo "Pre-stage with:  $(PYTHON) -c 'import cmdstanpy; cmdstanpy.install_cmdstan()'"

# ── Pipeline steps (run in order) ─────────────────────────────────────────────
ingest:
	$(PYTHON) -m src.ingest_edgar --ticker $(TICKER)

warehouse:
	$(PYTHON) -m src.build_warehouse --ticker $(TICKER)

model:
	$(PYTHON) -m papermill notebooks/02_baseline_forecast.ipynb /dev/null \
		-p ticker $(TICKER)

forecast:
	$(PYTHON) -m papermill notebooks/03_macro_regularized_forecast.ipynb /dev/null \
		-p ticker $(TICKER)
	$(PYTHON) -m src.build_variance_facts --ticker $(TICKER)

dashboard:
	$(PYTHON) -m src.build_excel_model --ticker $(TICKER)
	$(PYTHON) -m src.export_for_tableau --ticker $(TICKER)

# Pass LIVE=1 to actually call the Anthropic API; dry-run by default.
commentary:
	$(PYTHON) -m src.generate_commentary $(if $(LIVE),,--dry-run) --ticker $(TICKER)

notebooklm:
	$(PYTHON) -m src.build_notebooklm_bundle --ticker $(TICKER)

# ── Quality gates ─────────────────────────────────────────────────────────────
test:
	$(PYTHON) -m pytest tests/ -v

eval:
	$(PYTHON) -m pytest tests/eval/ -v

lint:
	$(PYTHON) -m ruff check src/ tests/
	$(PYTHON) -m ruff format --check src/ tests/

typecheck:
	$(PYTHON) -m mypy --strict src/

qa: lint typecheck test eval

# ── End-to-end demo ───────────────────────────────────────────────────────────
# Defaults to PANW. Switch ticker: make demo TICKER=CRWD
# Requires ANTHROPIC_API_KEY in .env for LIVE=1 commentary.
demo:
	@echo ">>> End-to-end demo: $(TICKER)"
	$(MAKE) ingest    TICKER=$(TICKER)
	$(MAKE) warehouse TICKER=$(TICKER)
	$(MAKE) model     TICKER=$(TICKER)
	$(MAKE) forecast  TICKER=$(TICKER)
	$(MAKE) dashboard TICKER=$(TICKER)
	$(MAKE) commentary TICKER=$(TICKER)
	$(MAKE) notebooklm TICKER=$(TICKER)
	$(MAKE) test
	$(MAKE) eval

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	rm -rf .venv __pycache__ .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} +
