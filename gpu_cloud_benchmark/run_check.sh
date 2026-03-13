#!/usr/bin/env bash
# Run setup check with a Python that works. Use this if "python run_comparison.py --check" shows no output.
# (Often the venv's python fails with ENOEXEC; python3 from PATH usually works.)

set -e
cd "$(dirname "$0")"

echo "=========================================="
echo "GPU Cloud Benchmark — setup check"
echo "=========================================="

# Prefer python3 from PATH (often works when venv python does not)
if command -v python3 &>/dev/null; then
  PYTHON=python3
elif command -v python &>/dev/null; then
  PYTHON=python
else
  echo "Error: No python3 or python found in PATH"
  exit 1
fi

echo "Using: $PYTHON = $($PYTHON -c 'import sys; print(sys.executable)')"
echo ""

$PYTHON run_comparison.py --check

echo ""
echo "=========================================="
echo "Done. Check above for PASS/FAIL."
echo "=========================================="
