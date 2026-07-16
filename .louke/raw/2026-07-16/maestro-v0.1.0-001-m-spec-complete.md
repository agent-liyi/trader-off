---
date: 2026-07-16
session: maestro-v0.1.0-001-m-spec-complete
agents: [Maestro, Sage, Lex, general-as-Lex]
spec: v0.1.0-001-lgbm-asset-pricing
related_issues: [#6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28]
status: resolved
---

## Topic
M-SPEC (Define Requirements) stage completion for trader-off — Sage↔Lex iteration, spec lock, issue creation, and full Lex verification.

## Decision
- **Spec locked**: `locked: true` in spec.md frontmatter (2026-07-16T08:37:02Z)
- **23 FR/NFR** (FR-0100~FR-1600, NFR-0100~NFR-0700), **79 AC** total
- **9 inline-discussion threads** all [RESOLVED]
- **23 GitHub issues** created (#6-#28), all linked to Project #3 (trader-off-v0.1.0)
- **23 HTML anchors** added to spec.md + acceptance.md for issue linking
- **All Lex checks passed**: quote-check exit 0, verify-acceptance L1-L5, verify-issue L1-L8, verify-project
- **Stage advance**: `lk agent maestro advance --stage M-SPEC` → advanced to M-TESTPLAN

Key spec decisions (from Sage↔Lex iteration):
- FR-1600 added: visualization output (3 static PNGs: NAV curve, IC time series, feature importance Top 20)
- Limit up/down filtering: use fetcher's `limit_up`/`limit_down` boolean fields (not hardcoded 0.095 threshold)
- NFR-0100 AC-1 split: mock unit test (4500 virtual assets) + @pytest.mark.integration test
- on_day_open chosen over on_day_close (user confirmed in M-SPEC Step 1)
- Walk-forward splits: train=3yr / valid=H1 / test=H2
- Long-only Top 20 equal-weight, daily rebalance

## Tried but abandoned
- **Lex agent model `kimi-k2.7-code` unavailable**: "Model not found" error. Used `general` agent as proxy for both Lex Stage 1 and Stage 2+3. Config files (.opencode/agents/lex.md, devon.md, shield.md) updated to `deepseek/deepseek-v4-pro`, but opencode caches agent config at session start — requires restart to take effect.
- **Sage Step 3 `lk discuss set-status` limitation**: operator must = initiator (Lex); Sage couldn't directly mark [RESOLVED]. Workaround: edit tool to add `[RESOLVED]` marker to root comment line.
- **Sage Step 5 first `create-issues` attempt**: failed silently (repo missing `Feature` label). Fixed by `gh label create Feature --color 0e8a16`, then re-ran create-issues.

## Open questions
- **opencode restart needed**: lex/devon/shield model change to `deepseek/deepseek-v4-pro` won't take effect until opencode restarts. In current session, these agents still use cached `kimi-k2.7-code`. Must use `general` agent as proxy until restart.
- **librarian model `MiniMax-M2.7` unverified**: not on critical path (daily knowledge distillation), but should verify when convenient.
- Proceeding to M-TESTPLAN: Archer (model `zhipuai-coding-plan/glm-5.2`, verified ✅) generates test-plan.md.
