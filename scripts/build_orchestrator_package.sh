#!/usr/bin/env bash
# =============================================================================
# build_orchestrator_package.sh
#
# Builds a self-contained, deployable package for the Orchestrator service.
#
# The output is a single zip (dist/orchestrator.zip) that contains:
#   - All pip-installed dependencies (site-packages flattened at zip root)
#   - The `shared` package (installed as a proper Python package)
#   - All orchestrator service source files (app.py, database.py, etc.)
#
# This zip can be used for:
#   ECS / Fargate   — alongside the Dockerfile (Docker handles this path)
#   AWS Lambda      — upload directly; set handler to `lambda_handler.handler`
#   ZIP deployment  — unzip onto any Linux Python 3.11 runtime and run app.py
#
# ─── Lambda notes ────────────────────────────────────────────────────────────
# FastAPI requires an ASGI↔Lambda bridge.  Add `mangum` to requirements.txt
# and create a thin lambda_handler.py wrapper (template included below).
# Lambda cannot use long-lived uvicorn processes; use Mangum instead of
# `uvicorn app:app` for the Lambda path.
# ─────────────────────────────────────────────────────────────────────────────
#
# Usage:
#   ./scripts/build_orchestrator_package.sh
#   ./scripts/build_orchestrator_package.sh --lambda    # adds Mangum
#   ./scripts/build_orchestrator_package.sh --platform linux/arm64  # Graviton
#
# Requirements: Python 3.11+, pip, zip (macOS/Linux)
# =============================================================================

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_DIR="$REPO_ROOT/services/orchestrator"
SHARED_DIR="$REPO_ROOT/shared"
BUILD_DIR="$REPO_ROOT/.build/orchestrator"
DIST_DIR="$REPO_ROOT/dist"
OUTPUT_ZIP="$DIST_DIR/orchestrator.zip"
PYTHON="${PYTHON:-python3}"
PIP_PLATFORM=""
LAMBDA_MODE=false

# ── Parse arguments ───────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --lambda)
      LAMBDA_MODE=true
      ;;
    --platform=*)
      PIP_PLATFORM="${arg#*=}"
      ;;
    *)
      echo "Unknown argument: $arg"
      exit 1
      ;;
  esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo "  ▸ $*"; }
step() { echo; echo "── $* ──────────────────────────────────"; }

# ── Start ─────────────────────────────────────────────────────────────────────
echo
echo "╔══════════════════════════════════════════════════╗"
echo "║  Orchestrator Package Builder                    ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Repo   : $REPO_ROOT"
echo "  Output : $OUTPUT_ZIP"
echo "  Lambda : $LAMBDA_MODE"
[ -n "$PIP_PLATFORM" ] && echo "  Target : $PIP_PLATFORM"
echo

# ── 1. Clean build directory ──────────────────────────────────────────────────
step "1. Cleaning build directory"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"
log "Build directory: $BUILD_DIR"

# ── 2. Install pip dependencies into build/package/ ──────────────────────────
# Packages are installed flat (--target) so zip root contains them directly.
step "2. Installing pip dependencies"
PACKAGE_DIR="$BUILD_DIR/package"
mkdir -p "$PACKAGE_DIR"

PIP_EXTRA_ARGS=""
if [ -n "$PIP_PLATFORM" ]; then
  # Cross-compile for a specific platform (e.g. linux/arm64 for Graviton Lambda)
  PIP_EXTRA_ARGS="--platform $PIP_PLATFORM --only-binary=:all: --implementation cp --python-version 311"
  log "Cross-compiling for platform: $PIP_PLATFORM"
fi

# shellcheck disable=SC2086
$PYTHON -m pip install \
  --quiet \
  --no-cache-dir \
  --target "$PACKAGE_DIR" \
  $PIP_EXTRA_ARGS \
  -r "$SERVICE_DIR/requirements.txt"

log "pip dependencies installed"

# ── 3. Install shared as a package ───────────────────────────────────────────
# `pip install ./shared` reads shared/pyproject.toml, finds the `shared` Python
# package in the parent directory (repo root), and installs it into PACKAGE_DIR.
step "3. Installing shared library"
$PYTHON -m pip install \
  --quiet \
  --no-cache-dir \
  --target "$PACKAGE_DIR" \
  "$SHARED_DIR"

log "shared package installed"

# ── 4. Copy orchestrator service source files ─────────────────────────────────
step "4. Copying orchestrator source files"

# Patterns to exclude (tests, compiled bytecode, local state, temp files)
EXCLUDE_PATTERNS=(
  "__pycache__"
  "*.pyc"
  "*.pyo"
  "*.py[cod]"
  "*.egg-info"
  "workflows.db"        # local SQLite db — never bundle
  "audit_logs"
  ".env"                # secrets must come from environment / Secrets Manager
  ".env.*"
  "*.log"
  "wstest*"
  "websocket_test_client.html"
  "migrate_*.py"        # migration scripts are run separately
)

# Build an rsync exclude string
RSYNC_EXCLUDES=()
for pat in "${EXCLUDE_PATTERNS[@]}"; do
  RSYNC_EXCLUDES+=(--exclude="$pat")
done

if command -v rsync &>/dev/null; then
  rsync -a "${RSYNC_EXCLUDES[@]}" "$SERVICE_DIR/" "$PACKAGE_DIR/"
else
  # Fallback: plain copy then manual cleanup
  cp -r "$SERVICE_DIR/." "$PACKAGE_DIR/"
  find "$PACKAGE_DIR" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
  find "$PACKAGE_DIR" -name "*.pyc" -delete 2>/dev/null || true
  rm -f "$PACKAGE_DIR/workflows.db" "$PACKAGE_DIR/.env" "$PACKAGE_DIR/.env.*"
fi

log "Service source files copied"

# ── 5. (Lambda mode) — add Mangum ASGI adapter + handler shim ────────────────
if [ "$LAMBDA_MODE" = true ]; then
  step "5. Lambda mode — adding Mangum adapter"

  $PYTHON -m pip install --quiet --no-cache-dir --target "$PACKAGE_DIR" mangum
  log "mangum installed"

  # Write a thin Lambda handler that wraps the FastAPI app via Mangum.
  cat > "$PACKAGE_DIR/lambda_handler.py" << 'LAMBDA_HANDLER'
"""
Lambda entry point for the Orchestrator service.

Mangum translates AWS Lambda API Gateway / Function URL events into ASGI calls
that FastAPI understands.  The `lifespan="off"` mode is used because Lambda
invocations are stateless — long-lived startup/shutdown hooks are not supported.
For warm-start state sharing use Redis (HA_BACKEND=redis) or DynamoDB.

Handler reference (Lambda console / SAM / CDK / Terraform):
    lambda_handler.handler
"""
from mangum import Mangum
from app import app  # FastAPI application instance

# lifespan="off" disables @asynccontextmanager lifespan for Lambda.
# Set to "on" only if you initialise all state lazily (no background tasks).
handler = Mangum(app, lifespan="off")
LAMBDA_HANDLER

  log "lambda_handler.py created (entry point: lambda_handler.handler)"
fi

# ── 6. Remove dist-info and test directories to slim the zip ─────────────────
step "$((LAMBDA_MODE && 5 || 5)). Cleaning installed metadata"
find "$PACKAGE_DIR" \
  \( -name "*.dist-info" -o -name "*.egg-info" -o -name "tests" -o -name "test" \) \
  -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# ── 7. Create the zip ─────────────────────────────────────────────────────────
step "6. Creating zip archive"
(
  cd "$PACKAGE_DIR"
  zip -q -r "$OUTPUT_ZIP" .
)

# ── Summary ────────────────────────────────────────────────────────────────────
ZIP_SIZE=$(du -sh "$OUTPUT_ZIP" | cut -f1)
echo
echo "╔══════════════════════════════════════════════════╗"
echo "║  Build complete ✓                                ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Output : $OUTPUT_ZIP"
echo "  Size   : $ZIP_SIZE"
if [ "$LAMBDA_MODE" = true ]; then
  echo
  echo "  Lambda deployment:"
  echo "    aws lambda update-function-code \\"
  echo "      --function-name orchestrator \\"
  echo "      --zip-file fileb://dist/orchestrator.zip"
  echo
  echo "  Handler :  lambda_handler.handler"
  echo "  Runtime :  python3.11"
  echo "  Env vars:  HA_BACKEND, REDIS_URL, AWS_REGION, BEDROCK_MODEL_ID, ..."
fi
echo
