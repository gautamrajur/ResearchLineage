#!/bin/bash
# ==============================================================================
# ResearchLineage - Test Runner Script
# ==============================================================================
# Runs all test cases with coverage reporting
#
# Usage:
#   ./scripts/run_tests.sh           # Run all tests with coverage
#   ./scripts/run_tests.sh --unit    # Run only unit tests
#   ./scripts/run_tests.sh --int     # Run only integration tests
#   ./scripts/run_tests.sh --fast    # Run tests without coverage (faster)
#   ./scripts/run_tests.sh --ci      # CI mode: strict, XML reports
# ==============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}  ResearchLineage - Test Runner${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

# Default settings
TEST_PATH="tests/"
COVERAGE_OPTS="--cov=src --cov-report=html --cov-report=term-missing"
PYTEST_OPTS="-v"
CI_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --unit)
            TEST_PATH="tests/unit/"
            echo -e "${YELLOW}Running: Unit tests only${NC}"
            shift
            ;;
        --int|--integration)
            TEST_PATH="tests/integration/"
            echo -e "${YELLOW}Running: Integration tests only${NC}"
            shift
            ;;
        --fast)
            COVERAGE_OPTS=""
            echo -e "${YELLOW}Running: Fast mode (no coverage)${NC}"
            shift
            ;;
        --ci)
            CI_MODE=true
            COVERAGE_OPTS="--cov=src --cov-report=xml --cov-report=term-missing --cov-fail-under=70"
            PYTEST_OPTS="-v --tb=short --strict-markers"
            echo -e "${YELLOW}Running: CI mode (strict, XML reports)${NC}"
            shift
            ;;
        --help|-h)
            echo "Usage: ./scripts/run_tests.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --unit        Run only unit tests"
            echo "  --int         Run only integration tests"
            echo "  --fast        Skip coverage reporting (faster)"
            echo "  --ci          CI mode: strict checks, XML reports, min coverage 70%"
            echo "  --help        Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Check if pytest is available
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest not found. Install with: pip install pytest pytest-cov${NC}"
    exit 1
fi

# Print configuration
echo -e "${BLUE}Configuration:${NC}"
echo "  Project Root: $PROJECT_ROOT"
echo "  Test Path:    $TEST_PATH"
echo "  Coverage:     ${COVERAGE_OPTS:-disabled}"
echo ""

# Run tests
echo -e "${BLUE}------------------------------------------------------------${NC}"
echo -e "${BLUE}Running Tests...${NC}"
echo -e "${BLUE}------------------------------------------------------------${NC}"
echo ""

# Build the pytest command
PYTEST_CMD="pytest $TEST_PATH $PYTEST_OPTS $COVERAGE_OPTS"

echo -e "${YELLOW}Command: $PYTEST_CMD${NC}"
echo ""

# Execute tests
if $PYTEST_CMD; then
    echo ""
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}  ✅ ALL TESTS PASSED${NC}"
    echo -e "${GREEN}============================================================${NC}"
    
    if [[ -n "$COVERAGE_OPTS" && "$CI_MODE" == false ]]; then
        echo ""
        echo -e "${BLUE}Coverage report generated: htmlcov/index.html${NC}"
        echo -e "${BLUE}Open with: open htmlcov/index.html${NC}"
    fi
    
    exit 0
else
    echo ""
    echo -e "${RED}============================================================${NC}"
    echo -e "${RED}  ❌ TESTS FAILED${NC}"
    echo -e "${RED}============================================================${NC}"
    exit 1
fi
