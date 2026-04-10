#!/usr/bin/env bash
# tests/run_all_tests.sh — Auto-validation script for StegoForge
# Run from project root: bash tests/run_all_tests.sh

set -e

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$PROJ_DIR/venv"
PYTHON="$VENV/bin/python"
PYTEST="$VENV/bin/pytest"

if [ ! -f "$PYTHON" ]; then
  echo "[ERROR] Python venv not found at $VENV"
  echo "  Run: python -m venv venv && venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          StegoForge — Full Test Suite                    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Generate fixtures
echo "[STEP 1/3] Generating test fixtures..."
cd "$PROJ_DIR"
"$PYTHON" tests/generate_fixtures.py
echo ""

# Step 2: Run pytest
echo "[STEP 2/3] Running pytest..."
"$PYTEST" tests/ \
  --tb=short \
  -v \
  --ignore=tests/integration_test.py \
  -p no:warnings \
  2>&1
PYTEST_EXIT=$?
echo ""

# Step 3: Run integration test
echo "[STEP 3/3] Running integration test..."
"$PYTHON" tests/integration_test.py
INTEGRATION_EXIT=$?
echo ""

# Final summary
echo "────────────────────────────────────────────────────────────"
if [ $PYTEST_EXIT -eq 0 ] && [ $INTEGRATION_EXIT -eq 0 ]; then
  echo "✓ ALL TESTS PASSED — StegoForge is production-ready!"
else
  echo "✗ Some tests failed."
  echo "  pytest exit: $PYTEST_EXIT"
  echo "  integration exit: $INTEGRATION_EXIT"
fi
echo "────────────────────────────────────────────────────────────"
echo ""
exit $(( PYTEST_EXIT + INTEGRATION_EXIT ))
