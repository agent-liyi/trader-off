---
date: 2026-07-25
session: sage-v0.7.4-001-version-flag-m-spec
agents: [Sage]
spec: v0.7.4-001-version-flag
related_issues: ["#181", "#182"]
status: resolved
supersedes: []
---

## Topic

M-SPEC clarification and issue creation for the v0.7.4 CLI version-flag patch.

## Decision

- The authoritative CLI scope is exactly the 15 `[project.scripts]` entries in `pyproject.toml`.
- Standalone `<command> --version` must exit 0, emit exactly `trader-off-<name> v0.7.4\n` to stdout, and emit empty stderr.
- Combining `--version` with other arguments and adding `-V` are outside acceptance.
- Both `src/trader_off/__init__.py` and `pyproject.toml` must carry `0.7.4`; runtime CLI formatting consumes `trader_off.__version__`.
- Inherited NFR-0100 applies function-scope lazy importing to `quantide`; standard-library and project-internal version-helper imports may remain module scoped.
- FR-0100 and FR-0200 are tier A and map to separate issues #181 and #182. NFR-0100 has no separate issue.
- Generated and pushed `.louke/project/specs/v0.7.4-001-version-flag/spec.md` and `acceptance.md` in commit `818acc6`.
- `lk agent sage quote-check --spec v0.7.4-001-version-flag` returned exit code 0 with zero threads.
- User reviewed the files in the IDE and explicitly authorized issue creation without `record-lock`.

## Tried but abandoned

- A normal `create-issues --dry-run` selected FR and NFR headings and would have created three issues. Because the user explicitly requested only the two FR issues, Sage used the command's `--spec-file` option with a temporary FR-only heading list; the resulting dry run selected exactly FR-0100 and FR-0200.
- `commit-spec` after IDE review found no spec-file changes and therefore made no second commit.

## Open questions

None. `record-lock` was intentionally not run and `locked: false` remains unchanged.
