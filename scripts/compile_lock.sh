#!/usr/bin/env bash
# Regenerate the lock files from requirements*.txt. Requires network access and `uv` (or pip-tools).
#   ./scripts/compile_lock.sh
#
# Both files are *universal* locks for the supported range (python_requires >= 3.10): one
# resolution that carries environment markers, so the same file installs on 3.10 and on 3.14.
#   requirements.lock       readable pins, no hashes
#   requirements.hash.lock  pins + sha256 hashes, for `pip install --require-hashes -r ...`
set -euo pipefail
cd "$(dirname "$0")/.."

SRC=(requirements.txt requirements-web.txt)
# Resolve from scratch: an existing output file would otherwise be read back in as preferred pins.
rm -f requirements.lock requirements.hash.lock
if command -v uv >/dev/null 2>&1; then
  uv pip compile "${SRC[@]}" --universal --python-version 3.10 --no-header --annotation-style line \
      -o requirements.lock
  uv pip compile "${SRC[@]}" --universal --python-version 3.10 --generate-hashes --no-header \
      -o requirements.hash.lock
else
  echo "uv not found; falling back to pip-tools (resolves for the CURRENT interpreter only)" >&2
  python -m pip install -q pip-tools
  python -m piptools compile --strip-extras --output-file=requirements.lock "${SRC[@]}"
  python -m piptools compile --generate-hashes --allow-unsafe --strip-extras \
      --output-file=requirements.hash.lock "${SRC[@]}"
fi
echo "wrote requirements.lock and requirements.hash.lock"
