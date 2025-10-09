# SPI Agent

AI-powered GitHub management for OSDU SPI services. Chat with your repositories using natural language.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

SPI Agent provides a conversational interface for managing GitHub **Issues**, **Pull Requests**, **Workflows**, and **Code Scanning** across OSDU SPI service repositories. Perform comprehensive GitHub operations without leaving your terminal.

**21 GitHub Tools Available:**
- 🐛 **Issues**: List, read, create, update, comment, search
- 🔀 **Pull Requests**: List, read, create, update, merge, comment
- ⚙️ **Workflows**: List, monitor runs, trigger, cancel
- 🔒 **Code Scanning**: List security alerts, get vulnerability details

```bash
You: List all open issues in partition
Agent: Here are the open issues in danielscholl-osdu/partition:

• #2: Configure MCP Server for GitHub Copilot Agent [human-required]

You: Tell me about issue #2
Agent: Here are the details for the open issue in danielscholl-osdu/partition:

• Issue: #2 — Configure MCP Server for GitHub Copilot Agent
• State: open
• Author: github-actions[bot]
• Labels: human-required
• Created / Updated: 2025-10-06T20:21:31+00:00

You: Look at https://github.com/danielscholl-osdu/partition/security/code-scanning/5
Agent: 🔴 Code Scanning Alert #5: SQL Injection Vulnerability
       State: Open | Severity: High
       File: src/api/query.js:42-45

       Unsanitized user input flows into SQL query construction...

       Would you like me to create a tracking issue for this security finding?

You: /fork partition
Agent: -- Custom workflow results --

You: /status legal
Agent: -- Custom workflow results --
```

## Prerequisites

**Azure Requirements**
- [Azure Foundry OpenAI](https://learn.microsoft.com/en-us/azure/ai-foundry/quickstarts/get-started-code?tabs=azure-ai-foundry)
- [Github Copilot CLI](https://github.com/github/copilot-cli)

**Required**
- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- [GitHub CLI](https://github.com/cli/cli#installation) + `gh auth login`



## Install & Configure

### 1. Install the package

**Recommended: Global Tool Installation**

```bash
uv tool install --prerelease=allow git+https://github.com/danielscholl-osdu/spi-agent.git
```
This installs `spi-agent` globally with isolated dependencies. You can then use `spi-agent` from anywhere.

**Tool Management Commands**
```bash
# List installed tools
uv tool list

# Upgrade to latest version
uv tool upgrade spi-agent

# Uninstall cleanly
uv tool uninstall spi-agent

# Reinstall (useful for troubleshooting)
uv tool uninstall spi-agent && uv tool install --prerelease=allow git+https://github.com/danielscholl-osdu/spi-agent.git
```

**For Development: Clone and install locally**

```bash
# Clone the repository
git clone https://github.com/danielscholl-osdu/spi-agent.git
cd spi-agent

# Option 1: Install as global tool (recommended)
uv tool install --prerelease=allow -e ".[dev]"
```

> **Note:** The package depends on `agent-framework>=1.0.0b251001`; `--prerelease=allow` ensures that build is selected.

### 2. Configure credentials

Copy `.env.example` to `.env` (or add to your shell profile) and fill in the values:

```bash
cp .env.example .env
```

The agent prefers environment variables, but will fall back to `az login` if no `AZURE_OPENAI_API_KEY` is present.


## Usage

### Basic Commands

**Interactive Chat Mode** (default)
```bash
spi-agent
```
Start a conversation with your repositories. Best for exploratory work and follow-up questions.

**Help**
```bash
spi-agent --help
```


## Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI resource URL | `https://my-resource.cognitiveservices.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Model deployment name | `gpt-5-mini` |
| `AZURE_OPENAI_VERSION` | API version | `2025-03-01-preview` |
| `AZURE_OPENAI_API_KEY` | API key | `your_api_key` |

### Optional Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SPI_AGENT_ORGANIZATION` | `danielscholl-osdu` | GitHub organization |
| `SPI_AGENT_REPOSITORIES` | `partition,legal,entitlements,schema,file,storage` | Comma-separated repo list |

## Testing

```bash
# Install dev dependencies
uv pip install -e ".[dev]" --prerelease=allow

# Run tests
pytest
```

## Documentation

- [📖 Technical Specification](specs/init_spec.md) - Complete architecture, tools, implementation plan, and acceptance criteria


## License

MIT License - See LICENSE file for details

## Acknowledgments

- Built with [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- Powered by [Azure AI Foundry](https://azure.microsoft.com/en-us/products/ai-services/ai-studio)
- Workflow automation via [GitHub Copilot CLI](https://www.npmjs.com/package/@github/copilot)
