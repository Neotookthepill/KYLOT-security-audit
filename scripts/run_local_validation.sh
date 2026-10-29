#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

PYTHONPATH=. ./.venv/bin/pytest -q \
  backend/test_security_invariants.py \
  backend/test_preflight.py \
  backend/test_app_smoke.py \
  backend/test_integration_security.py

for suite in \
  audit/security_adversarial_checks.py \
  audit/security_adversarial_round2.py \
  audit/security_adversarial_round3.py \
  audit/security_e2e_matrix.py \
  audit/security_hostile_inputs.py \
  audit/security_scale_checks.py \
  audit/security_route_business_fuzz.py
do
  PYTHONPATH=. ./.venv/bin/python "$suite"
done

./.venv/bin/python -m py_compile backend/server.py backend/preflight.py backend/migrate.py audit/*.py
./.venv/bin/bandit -q -r backend/server.py

cd frontend
CI=true ./node_modules/.bin/craco test --watchAll=false --runInBand
./node_modules/.bin/craco build

printf '%s\n' 'Validation locale réussie : 109 contrôles sécurité/robustesse, 40 tests serveur, 23 tests interface et build de production.'
