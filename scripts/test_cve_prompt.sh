#!/bin/bash
# Test CVE analysis prompt independently with copilot
#
# Usage:
#   ./scripts/test_cve_prompt.sh logs/triage_20251014_214958_partition-legal.log
#
# This allows you to iterate on the prompt without running full scans

if [ -z "$1" ]; then
    echo "Usage: $0 <log-file>"
    echo ""
    echo "Example:"
    echo "  $0 logs/triage_20251014_214958_partition-legal.log"
    echo ""
    echo "This will pipe the log file through copilot with the CVE analysis prompt"
    exit 1
fi

LOG_FILE="$1"
PROMPT_FILE="src/spi_agent/copilot/prompts/cve_analysis.md"

if [ ! -f "$LOG_FILE" ]; then
    echo "Error: Log file not found: $LOG_FILE"
    exit 1
fi

if [ ! -f "$PROMPT_FILE" ]; then
    echo "Error: Prompt file not found: $PROMPT_FILE"
    exit 1
fi

echo "Testing CVE analysis prompt..."
echo "Log file: $LOG_FILE"
echo "Prompt: $PROMPT_FILE"
echo ""
echo "Running copilot..."
echo ""

# Read the prompt template
PROMPT_TEMPLATE=$(cat "$PROMPT_FILE")

# Read the log file
LOG_CONTENT=$(cat "$LOG_FILE")

# Replace {{SCAN_RESULTS}} placeholder with actual log content
FULL_PROMPT="${PROMPT_TEMPLATE/\{\{SCAN_RESULTS\}\}/$LOG_CONTENT}"

# Run copilot with the populated prompt passed as argument
copilot -p "$FULL_PROMPT"
