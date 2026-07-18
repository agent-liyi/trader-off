#!/bin/bash
# =============================================================================
# Mutation Testing Script (NFR-0300)
# =============================================================================
# Runs mutmut mutation testing on trader_off source code.
#
# Usage:
#   ./scripts/run_mutation_tests.sh           # Run full mutation sweep
#   ./scripts/run_mutation_tests.sh --quick   # Quick run with fewer mutations
#   ./scripts/run_mutation_tests.sh --show    # Show mutation results
#
# Requirements:
#   - mutmut >= 2.0 must be installed (via uv pip install mutmut>=2.0)
#   - pytest must be installed
#
# NFR-0300 AC-1: mutation score >= 80% on src/trader_off/

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "================================================================================"
echo "Mutation Testing (NFR-0300)"
echo "================================================================================"

# Check if mutmut is installed
if ! command -v mutmut &> /dev/null; then
    echo -e "${RED}Error: mutmut is not installed.${NC}"
    echo "Install with: uv pip install mutmut>=2.0"
    exit 1
fi

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest is not installed.${NC}"
    exit 1
fi

# Parse arguments
QUICK=""
SHOW_RESULTS=""
case "${1:-}" in
    --quick)
        QUICK="--quick"
        echo -e "${YELLOW}Running in QUICK mode (fewer mutations)${NC}"
        ;;
    --show)
        SHOW_RESULTS="yes"
        echo -e "${YELLOW}Showing previous mutation results${NC}"
        ;;
esac

# Step 1: Create mutmut configuration if it doesn't exist
MUTMUT_CONFIG="$PROJECT_ROOT/.mutmutconfig"
if [ ! -f "$MUTMUT_CONFIG" ]; then
    echo -e "${YELLOW}Creating mutmut configuration...${NC}"
    cat > "$MUTMUT_CONFIG" << 'EOF'
# mutmut configuration for trader-off (NFR-0300)
# Minimal viable configuration

[mutmut]
paths = src/trader_off/
test_command = pytest tests/unit/
test_timeout = 60
no_progress = True
EOF
    echo -e "${GREEN}Created $MUTMUT_CONFIG${NC}"
fi

# Step 2: Run mutation testing
echo ""
echo -e "${YELLOW}Step 1: Collecting mutations...${NC}"
mutmut cache prune || true
mutmut run $QUICK --paths-to-mutate src/trader_off/ || {
    echo -e "${RED}Mutation run failed.${NC}"
    exit 1
}

echo ""
echo -e "${YELLOW}Step 2: Calculating mutation score...${NC}"
mutmut results || true

echo ""
echo -e "${YELLOW}Step 3: Showing mutation results summary...${NC}"
mutmut summary || true

echo ""
echo "================================================================================"
echo -e "${GREEN}Mutation testing complete!${NC}"
echo ""
echo "To view detailed results:"
echo "  mutmut show <mutation-id>"
echo ""
echo "To run full mutation sweep (may take hours):"
echo "  mutmut run --paths-to-mutate src/trader_off/"
echo "================================================================================"
