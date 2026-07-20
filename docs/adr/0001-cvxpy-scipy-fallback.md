# ADR-0001: cvxpy + scipy SLSQP Fallback for Portfolio Optimization

## Status

Accepted

## Context

Portfolio optimization (FR-3700) requires solving a Max Sharpe ratio convex optimization problem. We evaluated three approaches:

1. **cvxpy + ECOS** (default)
2. **scipy.optimize.SLSQP** (fallback)
3. **cvxpy only** (no fallback)

## Decision

We use **cvxpy with ECOS backend as default, automatically falling back to scipy.optimize.SLSQP** when cvxpy is unavailable or fails.

The fallback mechanism:
- On `import cvxpy`, set `HAS_CVXPY = True`
- If cvxpy import fails or solving returns an error, fall back to SLSQP
- Log at INFO level: `"cvxpy unavailable, fallback to scipy.optimize.SLSQP"`

## Consequences

**Positive:**
- Zero-dependency fallback ensures the optimizer never crashes in production
- ECOS backend provides strong solver performance for convex problems
- SLSQP fallback is battle-tested and widely available

**Negative:**
- cvxpy ~50MB installation overhead
- Fallback solver may have slightly different numerical precision

**Mitigation:**
- ImportError simulation tested via AC-FR3700-03
- Fallback uses SLSQP with default parameters + 1000 max iterations
