---
date: 2026-07-25
spec: v0.7.6-001-strategy-templates
status: draft
---

# v0.7.6 — Strategy templates — Acceptance Criteria

## FR-0100 — --template parameter

### AC-FR0100-01 — double-ma template
- **WHEN** `to generate-strategy --name X --template double-ma --dry-run` is run
- **THEN** generated code contains `self._fast`, `self._slow`, MA computation, and trade_target_pct calls

### AC-FR0100-02 — momentum template
- **WHEN** `to generate-strategy --name X --template momentum --dry-run` is run
- **THEN** generated code contains `self._lookback`, `self._top_k`, returns ranking

### AC-FR0100-03 — multi-factor template
- **WHEN** `to generate-strategy --name X --template multi-factor --dry-run` is run
- **THEN** generated code contains `self._w_mom`, `self._w_vol`, z-score normalization

### AC-FR0100-04 — unknown template
- **WHEN** `to generate-strategy --name X --template unknown` is run
- **THEN** exit code 2 and error message listing available templates

### AC-FR0100-05 — backward compatible (no template)
- **WHEN** `to generate-strategy --name X` is run without `--template`
- **THEN** skeleton with empty lifecycle methods is generated (same as v0.5.8)
