# SPI Unified CLI

Single entry point for all OSDU SPI management tasks - combines natural language GitHub issue management with copilot-powered workflows.

## Overview

`spi.py` is a unified CLI that provides three modes of operation:

1. **Interactive Chat** - Natural language conversations about GitHub issues
2. **One-Shot Queries** - Quick GitHub queries without entering chat mode
3. **Copilot Workflows** - Fork repos and check status using copilot automation

## Quick Start

```bash
# Interactive chat mode (default)
uv run --prerelease=allow spi-agent/spi.py

# One-shot query
uv run --prerelease=allow spi-agent/spi.py -p "How many issues in partition?"

# Fork repositories
uv run --prerelease=allow spi-agent/spi.py fork --services partition

# Check GitHub status
uv run --prerelease=allow spi-agent/spi.py status --services partition,legal
```

## Usage Modes

### 1. Interactive Chat Mode (Default)

Start a conversational session with the agent:

```bash
uv run --prerelease=allow spi-agent/spi.py
```

**Features:**
- 🎨 Beautiful Rich console UI
- 💬 Multi-turn conversations with context
- 📝 Markdown-formatted responses
- 🧠 Remembers conversation within session
- ⚡ Thinking status indicators

**Example Session:**
```
🤖 SPI Agent - Interactive Mode
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Organization: danielscholl-osdu
Model: gpt-5-mini
Memory: ✗ Disabled

You: How many issues in partition?
[Agent thinking... ⏳]

╭─────────── Agent ───────────╮
│ There is 1 open issue...    │
│ #2: Configure MCP Server... │
╰─────────────────────────────╯

You: Tell me more about that issue
[Remembers we're talking about issue #2]

You: exit
```

### 2. One-Shot Query Mode

Run a single query and exit:

```bash
uv run --prerelease=allow spi-agent/spi.py -p "List issues in partition"
uv run --prerelease=allow spi-agent/spi.py -p "Show me issues labeled bug"
uv run --prerelease=allow spi-agent/spi.py -p "Search for CodeQL"

# Quiet mode (just the answer)
uv run --prerelease=allow spi-agent/spi.py -q -p "How many issues?"
```

### 3. Copilot Workflows

Delegates to copilot automation with split-panel live tracking:

**Fork Repositories:**
```bash
uv run --prerelease=allow spi-agent/spi.py fork --services partition
uv run --prerelease=allow spi-agent/spi.py fork --services partition,legal --branch main
uv run --prerelease=allow spi-agent/spi.py fork --services all
```

**Check Status:**
```bash
uv run --prerelease=allow spi-agent/spi.py status --services partition
uv run --prerelease=allow spi-agent/spi.py status --services partition,legal
uv run --prerelease=allow spi-agent/spi.py status --services all
```

## Natural Language Capabilities

**List Issues:**
- "List all open issues in partition"
- "Show me issues labeled bug in legal"
- "List closed issues in entitlements"

**Search:**
- "Search for CodeQL across all repositories"
- "Find issues mentioning authentication"

**Issue Details:**
- "Tell me about issue #2 in partition"
- "Show me issue #5 in legal with full details"

**Create Issues:**
- "Create an issue in partition: Fix authentication bug"
- "Create a bug report in legal: API returns 500 error"

**Update Issues:**
- "Close issue #2 in partition"
- "Add label 'bug' to issue #3 in legal"

**Comments:**
- "Add comment to issue #2 in partition: This is fixed in v1.2"
- "Comment on issue #5 in legal: Needs more investigation"

## Architecture

```
spi.py (unified entry point)
├── Chat Mode → SPI Agent (Agent Framework + Azure OpenAI)
│   ├── Natural language processing
│   ├── GitHub API calls via PyGithub
│   └── Rich console UI
│
├── Fork Mode → Delegates to programmable/copilot.py
│   ├── CopilotRunner class
│   ├── Split-panel live tracking
│   └── Auto-logging
│
└── Status Mode → Delegates to programmable/copilot.py
    ├── StatusRunner class
    ├── JSON parsing and validation
    └── Rich formatted output
```

## Requirements

- Python 3.11+
- GitHub Copilot CLI (for fork/status commands)
- Azure OpenAI access with gpt-5-mini or compatible deployment
- GitHub personal access token (set in GITHUB_TOKEN env var)

**Environment Variables:**
```bash
# Required for chat mode
export AZURE_OPENAI_ENDPOINT="https://your-resource.cognitiveservices.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5-mini"
export AZURE_OPENAI_VERSION="2025-03-01-preview"
export AZURE_OPENAI_API_KEY="your_key"
export GITHUB_TOKEN="ghp_your_token"

# Optional
export MEM0_API_KEY="m0_your_key"  # For persistent memory
export COPILOT_ORGANIZATION="your-org"  # For fork/status defaults
```

## Benefits of Unified CLI

**Before:**
```bash
# Had to remember different tools
programmable/copilot.py fork --services partition
programmable/copilot.py status --services partition
spi-agent/spi.py -p "List issues"
```

**After:**
```bash
# Single entry point for everything
spi.py fork --services partition
spi.py status --services partition
spi.py -p "List issues"
spi.py  # Interactive chat
```

## Tips

1. **Create an alias for easier use:**
   ```bash
   alias spi='uv run --prerelease=allow spi-agent/spi.py'

   # Then just:
   spi
   spi -p "List issues"
   spi fork --services partition
   ```

2. **Disable mem0 if it causes issues:**
   ```bash
   unset MEM0_API_KEY
   # Agent still works with thread-based memory (within session)
   ```

3. **Use quiet mode for scripting:**
   ```bash
   spi -q -p "How many issues in partition?" | grep -o '[0-9]'
   ```

4. **Logs are saved automatically:**
   - Fork/Status logs: `programmable/logs/`
   - Chat logs: Not saved (use script recording if needed)

## Troubleshooting

### "Copilot module not available"
The fork/status commands require `programmable/copilot.py` to exist. Make sure you're running from the repo root.

### "Functions are not supported"
Your Azure OpenAI deployment doesn't support function calling. Use `gpt-5-mini`, `gpt-4o`, or `gpt-4o-mini`.

### Mem0 errors
If you see mem0 API errors, either:
- Unset `MEM0_API_KEY` to disable
- Or ignore - the agent will show a warning but continue working

### Agent not finding repositories
Check your environment variables are set correctly:
```bash
echo $AZURE_OPENAI_DEPLOYMENT_NAME
echo $AZURE_OPENAI_VERSION
echo $GITHUB_TOKEN
```
