# {Feature Title} — Spec

- **Spec ID**: {SPEC-ID}
- **Created**: {YYYY-MM-DD}
- **Status**: {Draft / Reviewing / Confirmed}

> **Responsibility split**: This document only describes the requirements themselves (FR/NFR descriptions + metadata).
> Acceptance criteria (observable, assertable pass conditions) live in `acceptance.md` so they can grow without bloating spec.
> The test plan (`test-plan.md`) references both spec.md and acceptance.md as inputs.

## User Stories

### US-0010
story: As a {role}, I want {feature}, so that {value}
priority: P0

### US-0020
story: As a {role}, I want {feature}, so that {value}
priority: P0

## Usage Scenarios

### scenario-0010

{Describe how the user should use this software}

## Functional Requirements

> **Format convention (must read)**: Each FR unit starts with a level-3 heading + space + FR-XXXX (uppercase, 4-digit zero-padded) + {title}, immediately followed by a 3-column metadata table (Valid / Testable / Decided), then the requirement description; separate FRs with `---`.
>
> **Numbering convention (must read)**: FR codes use **4 digits**, zero-padded, **starting from 100 in the initial draft, stepping by 100** (FR-0001, FR-0101, FR-0201, ...); **after the first review round, insert by step 10** (FR-0011 between FR-0001 and FR-0101); **after the second round, use sequential numbering**. This 100/10/1 spacing reserves room for future insertions and avoids large-scale renumbering.
>
> **Must read**: The FR-XXXX code is the id of that requirement. Never delete an existing requirement id to avoid reference confusion; if a FR must be deprecated, change `Valid` to `❌` in the table and explain in the clarification log.
>
> **AC reference**: Acceptance criteria use the `AC-FRXXXX-YY` format (4-digit FR + 2-digit AC), see `acceptance.md`.
>
> **Metadata fields (table columns)**:
> - Valid (formerly yaml `valid`): `✅` = still active, `❌` = deprecated
> - Testable (formerly yaml `testability`): `✅` = can be tested/asserted, `⚠️ {reason}` = has reservations
> - Decided (formerly yaml `resolved`): `✅` = user approved, `⚠️` = pending clarification, `❌` = user explicitly rejected

### FR-0010 {title}

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

{Requirement description}

---

### FR-0020 {title}

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ⚠️ {reason} | ⚠️ |

{Requirement description}

---

## Non-Functional Requirements

> **Must read**: Format and numbering rules are the same as FR; omitted here.

### NFR-0010 {title}

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

{Requirement description}

---

## Clarification Log

> Record questions raised during user review, Sage/Lex replies, reasons for deprecated requirements, and any decisions that affect FR/NFR table status.
