"""Portfolio optimization module (v0.2.0 Module C).

Sub-modules:
    covariance:    Ledoit-Wolf / sample covariance estimation (FR-3000)
    expected_returns:  Expected returns input and validation (FR-3100)
    industry:      Industry map loading and conflict resolution (FR-3200)
    constraints:   Optimization constraints as data specs (FR-3300~3600)
    solver:        Max Sharpe optimization (cvxpy / scipy, FR-3700)
    check:         Post-solve constraint violation checks (FR-3800)
    baseline:      Equal-weight baseline comparison (FR-3900)
    persistence:   Atomic output persistence (FR-4000)
    cli:           optimize CLI (FR-4100)
"""
