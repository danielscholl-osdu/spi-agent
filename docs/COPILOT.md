# Copilot CLI Wrapper

Enhanced GitHub Copilot CLI automation wrapper with Rich console output and live progress tracking.

## Features

- 🎨 **Rich Console Output**: Beautiful formatted tables, panels, and progress indicators
- 📊 **Split-Panel Layout**: Side-by-side view with status table (left) and live output (right)
- 👁️ **Live Service Tracking**: Real-time status updates for each service being processed
- 🔄 **Streaming Output**: See copilot commands and output as they happen in dedicated panel
- 🎯 **Subcommand Pattern**: Clean CLI interface with argument parsing
- 📁 **External Prompts**: Easy-to-edit workflow definitions in `prompts/` directory
- ✅ **Status Summary**: Final report with success/error/skipped counts
- 🛡️ **Safety First**: Monitor all commands in real-time - Ctrl+C anytime if something looks wrong
- 📝 **Auto-Logging**: All executions automatically saved to `logs/` directory with timestamps
- ⚙️ **Configuration**: `.env` file support for customizing organization, template, and defaults
- ✨ **Data Validation**: Pydantic models ensure status JSON output matches expected schema
- 🔄 **Graceful Shutdown**: Clean process termination on Ctrl+C with proper cleanup

## Installation

This is a **single-file uv script** with inline dependencies. No installation required! Just run it with `uv`:

```bash
uv run copilot.py fork --services partition
```

`uv` will automatically install dependencies (rich, pydantic, python-dotenv) in an isolated environment.

## Configuration

### Optional: Create `.env` file

Customize defaults by creating a `.env` file in the `programmable/` directory:

```bash
cp .env.example .env
```

**Available settings:**

```bash
# GitHub Organization (default: danielscholl-osdu)
COPILOT_ORGANIZATION=your-org-name

# Template repository for forking (default: azure/osdu-spi)
COPILOT_TEMPLATE_REPO=your-org/your-template

# Default branch for operations (default: main)
COPILOT_DEFAULT_BRANCH=main

# Directory for execution logs (default: logs)
COPILOT_LOG_DIRECTORY=logs
```

**Note:** Configuration is optional. The script works with built-in defaults if no `.env` file exists.

## Usage

### Fork OSDU Services

Create forked repositories from the Azure OSDU SPI template:

```bash
# Fork a single service
uv run copilot.py fork --services partition

# Fork multiple services
uv run copilot.py fork --services partition,legal,entitlements

# Fork all services
uv run copilot.py fork --services all

# Fork with custom branch
uv run copilot.py fork --services partition --branch develop
```

### Check GitHub Status

Get GitHub status for forked services (issues, PRs, workflows, CodeQL):

```bash
# Check status of a single service
uv run copilot.py status --services partition

# Check multiple services
uv run copilot.py status --services partition,legal,entitlements

# Check all services
uv run copilot.py status --services all
```

**Information Gathered:**
- Open issues count and details
- Pull requests (highlights release PRs like "chore: release 1.0.0")
- Recent workflow runs (Build, Test, CodeQL, etc.)
- Workflow status (running, completed, failed)

**When to Use:**
- After forking services to check initialization status
- Monitor workflow progress (CodeQL, builds, tests)
- Check for open issues or pending PRs
- Anytime you want a GitHub overview

### Available Services

- `partition` - Partition Service
- `entitlements` - Entitlements Service
- `legal` - Legal Service
- `schema` - Schema Service
- `file` - File Service
- `storage` - Storage Service
- `indexer` - Indexer Service
- `indexer-queue` - Indexer Queue Service
- `search` - Search Service
- `workflow` - Workflow Service

## Output Example

The script displays a **split-panel layout** with status on the left and live output on the right:

```
╭────────────────────────── 🤖 Copilot Automation ──────────────────────────╮
│ Prompt: fork.md | Services: partition, legal | Branch: main               │
╰───────────────────────────────────────────────────────────────────────────╯

┏━━━━━━ Status Table ━━━━━━┓ ┏━━━━━━━━━━━━ 📋 Live Output ━━━━━━━━━━━━━━━━┓
┃ Service   │ Status       ┃ ┃ ● Check if partition repo exists           ┃
┃           │              ┃ ┃ $ gh repo view danielscholl-osdu/partition ┃
┃ ✓ part..  │ SUCCESS      ┃ ┃ ✓ Repository created                       ┃
┃           │ Completed    ┃ ┃ ✓ Wait for Initialize Fork workflow        ┃
┃ ⏳ legal   │ RUNNING      ┃ ┃ ✓ Read "Repository Initialization.." issue ┃
┃           │ Creating..   ┃ ┃ ✓ Comment on issue with upstream repo link ┃
┃                          ┃ ┃ ✓ Pull latest changes from partition repo  ┃
┃                          ┃ ┃ $ cd legal && gh run watch 18291111964..   ┃
┃                          ┃ ┃ [Rolling buffer of last 50 lines]          ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━┛ ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

When complete, left panel switches to final report:

┏━━━━━━━ 📊 Final Report ━━━━━━━┓ ┏━━━━━━━━━ 📋 Live Output ━━━━━━━━━━━┓
┃ ==================================== ┃ ┃                                   ┃
┃ ✓ Completed                          ┃ ┃ ✓ Verify git remote config        ┃
┃ ==================================== ┃ ┃ Perfect! Now let me go back...    ┃
┃                                      ┃ ┃ ✓ Return to parent directory      ┃
┃ Services:                            ┃ ┃                                   ┃
┃   ✓ partition       SUCCESS          ┃ ┃ Excellent! The repository has     ┃
┃      Completed successfully          ┃ ┃ been successfully updated with    ┃
┃   ✓ legal          SUCCESS           ┃ ┃ all the upstream content.         ┃
┃      Completed successfully          ┃ ┃                                   ┃
┃                                      ┃ ┃ [Full output history available]   ┃
┃ Summary:                             ┃ ┃                                   ┃
┃ ✓ Success:  2                        ┃ ┃                                   ┃
┃ ⊘ Skipped:  0                        ┃ ┃                                   ┃
┃ ✗ Errors:   0                        ┃ ┃                                   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛ ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

**Layout Benefits:**
- **Left panel**: Live status table during execution → Final report with details when complete
- **Right panel**: Full command visibility - see exactly what copilot is doing
- **Safety**: Monitor all gh/git commands in real-time, Ctrl+C if needed
- **Rolling buffer**: Keeps last 50 lines visible (auto-scrolls)
- **Smart parsing**: Detects copilot's task markers (✓, ✗) and narrative updates for accurate status tracking

### Status Command Output

The `status` command uses the same split-panel layout during execution:

**During Execution:**
- **Left panel**: Service status table showing which services are being queried
  - `⏸ PENDING` → Waiting to query
  - `🔍 QUERYING` → Currently gathering data (issues, PRs, workflows)
  - `✓ GATHERED` → Data collection complete
- **Right panel**: Live copilot activity (gh commands, API calls)

**Example During Execution:**
```
┏━━━ GitHub Data Gathering ━━━┓ ┏━━━━━━━━ 📋 Copilot Activity ━━━━━━━━━┓
┃ Service   │ Status          ┃ ┃ ✓ Check partition repository exists  ┃
┃           │                 ┃ ┃ $ gh repo view danielscholl-osdu/..  ┃
┃ 🔍 part.. │ QUERYING        ┃ ┃ ✓ Get partition repository issues    ┃
┃           │ Getting issues  ┃ ┃ $ gh issue list --repo daniel...      ┃
┃ ⏸ legal   │ PENDING         ┃ ┃ ✓ Get partition pull requests         ┃
┃           │ Waiting         ┃ ┃ $ gh pr list --repo danielscholl-..   ┃
┗━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━┛ ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

**After Completion:**
Displays comprehensive GitHub information in an organized format:

```
┏━━━━━━━━━━━━━━ 📊 GitHub Status Summary ━━━━━━━━━━━━━━┓
┃ Service    │ Issues │ PRs │ Workflows     │ Last Update ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ ✓ partition│ 1 open │ 1   │ ✓ 10 ok       │ 51m ago     │
│ ✓ legal    │ 1 open │ 1   │ ✓ 10 ok       │ 47m ago     │
└────────────┴────────┴─────┴───────────────┴─────────────┘

┏━━━━━━━━━━━━━━━ 🚀 Release Pull Requests ━━━━━━━━━━━━━━━┓
│ Service    │ PR                            │ Status      │
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ partition  │ #3: chore: release 1.0.0      │ OPEN        │
│ legal      │ #3: chore: release 1.0.0      │ OPEN        │
└────────────┴───────────────────────────────┴─────────────┘

┏━━━━━━━━━━━━━━ ⚙️ Recent Workflow Runs ━━━━━━━━━━━━━━━━┓
┃ Service    │ Workflow                 │ Status      │ When    ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━┩
│ partition  │ Build                    │ ✓ success   │ 50m ago │
│            │ CodeQL Analysis          │ ✓ success   │ 7m ago  │
│            │ Test                     │ ✓ success   │ 51m ago │
│            │ Release Management       │ ✓ success   │ 51m ago │
│ legal      │ Build                    │ ✓ success   │ 47m ago │
│            │ CodeQL Analysis          │ ✓ success   │ 3m ago  │
│            │ Test                     │ ✓ success   │ 47m ago │
└────────────┴──────────────────────────┴─────────────┴─────────┘

┏━━━━━━━━━━━━━━━━━━━ 📝 Open Issues ━━━━━━━━━━━━━━━━━━━━┓
│ #2 Configure MCP Server for GitHub Copilot Agent      │
│    Affects: partition, legal                           │
│    ⚠ Requires manual intervention                      │
│    Labels: human-required                              │
└────────────────────────────────────────────────────────┘

┏━━━━━━━━━━━━━━━━━━━ 💡 Next Steps ━━━━━━━━━━━━━━━━━━━━━┓
│ ⚠ Review issue #2: Configure MCP Server for GitHub... │
│   Services: partition, legal                           │
│ 🚀 Review 2 release PR(s) for merging                  │
│ ✓ All workflows completed                              │
└────────────────────────────────────────────────────────┘

Status retrieved at: 2025-10-06T21:13:51Z
```

**Key Improvements:**
- **Workflow Details**: See individual workflow runs with status and timing
- **Issue Grouping**: Duplicate issues shown once with "Affects: service1, service2"
- **Human-Required Highlighting**: Red warning for issues needing manual intervention
- **Next Steps**: Actionable summary of what to do next
- **Cleaner Layout**: All information scannable at a glance

## Logging

All executions are automatically logged to the `logs/` directory:

**Log File Naming:**
- Fork: `fork_YYYYMMDD_HHMMSS_service1-service2-service3.log`
- Status: `status_YYYYMMDD_HHMMSS_service1-service2-service3.log`

**Log Contents:**
- Timestamp and command parameters
- Full copilot output (all commands and responses)
- Exit code
- For status: Extracted and validated JSON data

**Example:**
```bash
$ uv run copilot.py fork --services partition
Logging to: logs/fork_20251006_213045_partition.log
...
✓ Log saved to: logs/fork_20251006_213045_partition.log
```

**Benefits:**
- Debug issues after execution
- Audit trail of all operations
- Share logs for troubleshooting
- Review what copilot actually did

## Project Structure

```
programmable/
├── copilot.py          # Main enhanced wrapper script
├── prompts/
│   ├── fork.md        # Fork workflow definition
│   └── status.md      # GitHub status gathering workflow
├── logs/              # Auto-generated execution logs (gitignored)
│   ├── fork_*.log
│   └── status_*.log
├── .env.example       # Configuration template
├── .env               # Your configuration (create from .env.example)
└── README.md          # This file
```

## Adding New Workflows

1. Create a new prompt file in `prompts/` directory
2. Add a subcommand in `copilot.py` (follow the `fork` pattern)
3. Map the subcommand to the prompt file

Example:

```python
# Add to subparsers in main()
deploy_parser = subparsers.add_parser('deploy', help='Deploy OSDU services')
deploy_parser.add_argument('--environment', required=True)
```

## How It Works

### Fork Command
1. **Argument Parsing**: Uses `argparse` for clean CLI with subcommands
2. **Prompt Loading**: Reads workflow definition from `prompts/fork.md`
3. **Argument Injection**: Adds `SERVICES` and `BRANCH` to the prompt
4. **Split Layout**: Creates side-by-side Rich Layout with status table and output panel
5. **Streaming Execution**: Runs `copilot` with `subprocess.Popen` for line-by-line output
6. **Rolling Buffer**: Maintains last 50 lines of output with color-coded formatting
7. **Live Tracking**: Parses output in real-time to update service status table
8. **Dual Updates**: Refreshes both panels simultaneously (4 times per second)
9. **Summary Display**: Shows final statistics and results

### Status Command
1. **Argument Parsing**: Parses services to check
2. **Prompt Loading**: Reads from `prompts/status.md`
3. **Split Layout**: Status tracker table (left) and copilot activity (right)
4. **Live Monitoring**: Tracks which services are being queried in real-time
5. **JSON Extraction**: Parses copilot's JSON output with multiple fallback strategies
6. **Pydantic Validation**: Validates JSON structure matches expected schema
7. **Auto-Logging**: Saves full output and extracted data to log files
8. **Rich Display**: Beautiful tables showing issues, PRs, workflows, and summary

## Requirements

- Python 3.11+
- GitHub Copilot CLI installed and authenticated (`gh extension install github/gh-copilot`)
- GitHub Copilot Pro/Business/Enterprise subscription
- `uv` package manager

**Dependencies (auto-installed by uv):**
- `rich==14.1.0` - Console formatting and UI
- `pydantic==2.10.6` - Data validation
- `python-dotenv==1.0.1` - Configuration management

## Troubleshooting

### "copilot command not found"

Install GitHub Copilot CLI:

```bash
gh extension install github/gh-copilot
```

### Service status not updating

The parser looks for keywords like "creating", "success", "error", "waiting" in copilot output. If copilot changes its output format, you may need to adjust the `parse_output_line()` method in copilot.py:168.
