# Testing CVE Analysis Prompt

## Quick Test Script

Use `test_cve_prompt.sh` to iterate on the CVE analysis prompt without running full scans.

### Usage

```bash
# After running a triage scan, test the prompt with its log file
./scripts/test_cve_prompt.sh logs/triage_20251014_214958_partition-legal.log
```

### What It Does

1. Reads the triage log file
2. Loads the CVE analysis prompt from `src/spi_agent/copilot/prompts/cve_analysis.md`
3. Replaces `{{SCAN_RESULTS}}` with the log content
4. Pipes the complete prompt to `copilot -p -`

### Benefits

- **Fast iteration**: Test prompt changes without re-running scans
- **Isolate prompt quality**: See exactly what the agent returns
- **Debug prompt issues**: Identify if results are due to prompt or data

### Example Workflow

```bash
# 1. Run a triage scan
spi-agent triage --services partition,legal

# 2. Note the log file path from output
# Logging to: logs/triage_20251014_214958_partition-legal.log

# 3. Edit the prompt
vim src/spi_agent/copilot/prompts/cve_analysis.md

# 4. Test your changes
./scripts/test_cve_prompt.sh logs/triage_20251014_214958_partition-legal.log

# 5. Repeat steps 3-4 until satisfied
```

### Manual Testing

If you prefer manual testing:

```bash
# Read the prompt template
PROMPT=$(cat src/spi_agent/copilot/prompts/cve_analysis.md)

# Read a log file
LOG=$(cat logs/triage_20251014_214958_partition-legal.log)

# Replace placeholder and pipe to copilot
echo "${PROMPT/\{\{SCAN_RESULTS\}\}/$LOG}" | copilot -p -
```

## Prompt Location

The CVE analysis prompt is at:
```
src/spi_agent/copilot/prompts/cve_analysis.md
```

Edit this file to improve:
- Output format
- Prioritization logic
- Filtering criteria
- Consolidation strategy
