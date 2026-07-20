---
date: 2026-07-20
session: judge-v0.2.0-001-security-audit
agents: [Judge]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: []
status: resolved
supersedes: []
---

## Topic
M-SECURITY deep audit for releases/v0.2.0 vs main (207 files, +7516/-76 in src).

## Decision
PASS. Stage-1 tool verdict was REJECT (exit 1) with 6 "critical" eval/exec + 1 medium logging finding — all refuted in stage-2 semantic review as false positives (re.compile() regex compilation; fake token in a PII-assertion test fixture). Real findings: 1 medium (unauthenticated retrain API bindable to non-loopback host via api_host config, scheduler/cli.py:118 + api.py), 2 low (task.error leaked verbatim in /retrain/status api.py:142; pre-existing joblib.load trust boundary training/serialize.py:144). No critical/high. Reports: .louke/raw/security-audit-20260720-134606.json (tool), .louke/project/stage-results/v0.2.0-001-factor-mining-retrain-optimizer/M-SECURITY/audit-result.json (stage artifact, created to match M-* convention).

## Tried but abandoned
- Considered flagging GC shutil.rmtree(models_dir / version) as path traversal — rejected: registry.json entries are locally trusted (writing them already implies FS access); orphan dirs are regex-validated so no traversal there.
- Considered flagging deploy_model pointer swap without on-disk artifact check — downgraded to informational: rollback_to validates registry membership and GC never deletes current version, so registry/disk stay consistent.

## Open questions
- Should api.py add a shared-token auth when api_host != 127.0.0.1? Left as medium recommendation for next milestone.
- Stage-1 pattern scanner should whitelist re.compile to cut false-positive noise (6/7 findings were noise).
