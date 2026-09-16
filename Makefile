# Entry points. Run `make` for the list.
PY := .venv/bin/python
API := http://127.0.0.1:8080

.DEFAULT_GOAL := help
.PHONY: help setup api web web-build web-test web-typecheck test lint synth quality-fit sim params docker deploy clean freeze holdout ablation explain smoke doctors approve-doctor whatsapp-check care-finder-check tunnel

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'

setup:  ## create the venv and install everything
	/opt/homebrew/opt/python@3.11/bin/python3.11 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -r requirements-dev.txt
	@echo "$(PWD)" > .venv/lib/python3.11/site-packages/sih_dr.pth
	cd web && npm install

api:  ## run the API on :8080
	$(PY) -m uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --reload

web:  ## run the frontend on :3000
	cd web && npm run dev

web-build:  ## production build of the frontend (refuses to run while `make web` is live)
	@if pgrep -f "next dev" > /dev/null; then \
	  echo "A Next.js dev server is running."; \
	  echo "'next build' and 'next dev' share web/.next — running both mixes production"; \
	  echo "and dev artifacts and produces 'Cannot find module ./NNN.js' at runtime."; \
	  echo ""; \
	  echo "Stop it first:  pkill -f 'next dev'"; \
	  echo "Then:           make web-build && rm -rf web/.next && make web"; \
	  exit 1; \
	fi
	cd web && npm run build

test:  ## run the test suite
	$(PY) -m pytest tests/ -q

web-test:  ## run the frontend tests (CareBridge language, voice and result presentation)
	cd web && npm test

web-typecheck:  ## type-check the frontend without building
	cd web && npx tsc --noEmit

synth:  ## regenerate the synthetic test images
	$(PY) scripts/make_synthetic_fundus.py

smoke:  ## end-to-end check against a running API (TOKEN=... for the authenticated part)
	@curl -sf $(API)/health | $(PY) -m json.tool
	@echo "-- access control (no token) --"
	@curl -s -o /dev/null -w "no token    -> HTTP %{http_code} (401 expected)\n" \
	  -F "file=@data/interim/synthetic/grade3_1.png" $(API)/v1/analyze
	@if [ -n "$(TOKEN)" ]; then \
	  echo "-- screening (with supplied token) --" ; \
	  curl -s -o /dev/null -w "good image  -> HTTP %{http_code} (200 expected)\n" \
	    -H "Authorization: Bearer $(TOKEN)" \
	    -F "file=@data/interim/synthetic/grade3_1.png" $(API)/v1/analyze ; \
	  curl -s -o /dev/null -w "blurry image-> HTTP %{http_code} (422 expected)\n" \
	    -H "Authorization: Bearer $(TOKEN)" \
	    -F "file=@data/interim/synthetic/bad_blur.png" $(API)/v1/analyze ; \
	else \
	  echo "-- screening: SKIPPED (no TOKEN) --" ; \
	  echo "   Twilio Verify owns the code, so there is no development OTP to mint one from." ; \
	  echo "   Sign in at the website, copy 'dr_session_token' from localStorage, then:" ; \
	  echo "     make smoke TOKEN=<token>" ; \
	fi

whatsapp-check:  ## verify Twilio WhatsApp setup (add TO=+91... to send a real message)
	$(PY) scripts/check_whatsapp.py $(if $(TO),--to $(TO),)

care-finder-check:  ## verify the Google Places setup (SUITE=1 for a full live run, or NEAR=/AREA=)
	$(PY) scripts/check_care_finder.py $(if $(SUITE),--suite,) $(if $(NEAR),--near $(NEAR),) $(if $(AREA),--area "$(AREA)",)

tunnel:  ## expose the API over HTTPS so Twilio can fetch report PDFs (restart the API after)
	scripts/dev_tunnel.sh

doctors:  ## list doctor accounts and their verification state
	$(PY) scripts/approve_doctor.py --list

approve-doctor:  ## approve a doctor account (needs MOBILE=+91XXXXXXXXXX)
	$(PY) scripts/approve_doctor.py --mobile $(MOBILE)

quality-fit:  ## fit the quality-gate thresholds (needs LABELS=path/to/labels.csv)
	$(PY) scripts/compare_focus_metrics.py --labels $(LABELS)
	$(PY) scripts/fit_quality_thresholds.py --labels $(LABELS) --provenance "$(PROVENANCE)"

train:  ## train (needs APTOS_CSV and APTOS_IMAGES)
	$(PY) -m src.grading.train --aptos-csv $(APTOS_CSV) --aptos-images $(APTOS_IMAGES) \
	  --out artifacts/model --epochs $(or $(EPOCHS),12)

freeze:  ## tune thresholds + fit temperature on VALIDATION, then freeze
	$(PY) scripts/calibrate_and_freeze.py --model-dir artifacts/model

holdout:  ## run the external holdout ONCE (needs IDRID_CSV, IDRID_IMAGES)
	$(PY) scripts/run_holdout.py --idrid-csv $(IDRID_CSV) --idrid-images $(IDRID_IMAGES)

ablation:  ## the ablation table (needs APTOS_CSV, APTOS_IMAGES)
	$(PY) scripts/run_ablation.py --aptos-csv $(APTOS_CSV) --aptos-images $(APTOS_IMAGES)

explain:  ## measured explainability (needs IDRID_IMAGES, IDRID_MASKS)
	$(PY) scripts/eval_explainability.py --images $(IDRID_IMAGES) --masks $(IDRID_MASKS)

params:  ## export measured service times for the workflow model
	$(PY) scripts/export_simulink_params.py --api $(API)

sim:  ## run the district workflow simulation
	$(PY) scripts/simulate_workflow.py

docker:  ## build the Cloud Run image locally (amd64, as Cloud Run runs)
	docker build --platform linux/amd64 -t dr-api:test .

deploy:  ## deploy the API to Cloud Run
	./scripts/deploy_cloudrun.sh

clean:  ## remove caches
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache web/.next
