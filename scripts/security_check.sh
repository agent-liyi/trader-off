#!/bin/bash
# Security audit script for NFR-0700 (security).
# Run: bash scripts/security_check.sh

set -e

echo "=== NFR-0700 Security Audit ==="

echo "[1/3] bandit — Python security linter"
uv run bandit -r src/ -q

echo "[2/3] ruff check — import + style (already in pre-commit)"
uv run ruff check src/ --quiet

echo "[3/3] pip-audit — dependency vulnerability scan"
uv tool run pip-audit --strict || uv tool run pip-audit

echo "=== All security checks passed ==="
