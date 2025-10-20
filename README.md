# SPI Agent

AI-powered GitHub & GitLab management for OSDU SPI services. Chat with your repositories using natural language.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

SPI Agent provides a conversational interface for managing **GitHub** and **GitLab** repositories across OSDU SPI services. Manage Issues, Pull/Merge Requests, Workflows/Pipelines, Code Scanning, and more. With Maven MCP integration, gain powerful **dependency management** and **security scanning** capabilities. Perform comprehensive multi-platform repository operations without leaving your terminal.

**48+ Tools Available** (when both platforms configured):

**GitHub:**
- 🐛 **Issues**: List, read, create, update, comment, search, **assign to Copilot**
- 🔀 **Pull Requests**: List, read, create, update, merge, comment
- ⚙️ **Workflows**: List, monitor runs, trigger, cancel, **detect approval required**
- 🔒 **Code Scanning**: List security alerts, get vulnerability details

**GitLab** (optional):
- 🐛 **Issues**: List, read, create, update, add notes, search
- 🔀 **Merge Requests**: List, read, create, update, merge, add notes
- ⚙️ **Pipelines**: List, monitor, trigger, cancel, retry, get jobs

**Common:**
- 📁 **File System**: List files, read contents, search patterns, parse POMs, find dependency versions
- 📦 **Maven Dependencies** (optional): Version checks, vulnerability scanning, triage analysis

```bash
You: List all open issues in partition
Agent: I found 1 open issue in partition:

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

You: /test partition
Agent: -- Maven test results --

You: The latest os-core-lib-azure version is 2.2.6. Locate services that aren't at the latest version.
Agent: Found 3 reference(s) to org.opengroup.osdu:os-core-lib-azure:

       Service: file
         repos/file/providers/azure/pom.xml
           Version: ${os-core-lib-azure.version} → 2.2.5
           Location: dependencies

       Service: partition
         repos/partition/providers/azure/pom.xml
           Version: 2.2.6
           Location: dependencies

       Service: legal
         repos/legal/providers/azure/pom.xml
           Version: 2.2.4
           Location: dependencies

       Services not at version 2.2.6: file (2.2.5), legal (2.2.4)
```

## Prerequisites

**Azure Requirements**
- [Azure Foundry OpenAI](https://learn.microsoft.com/en-us/azure/ai-foundry/quickstarts/get-started-code?tabs=azure-ai-foundry)
- [Github Copilot CLI](https://github.com/github/copilot-cli)

**Required**
- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- [GitHub CLI](https://github.com/cli/cli#installation) + `gh auth login`

**Optional (for Maven dependency management)**
- [trivy](https://trivy.dev) for security vulnerability scanning



## Install

Install `spi-agent` globally using `uv`:

```bash
# Install from GitHub
uv tool install --prerelease=allow git+https://github.com/danielscholl-osdu/spi-agent.git

# Upgrade to latest version
uv tool upgrade spi
```

The agent requires environment variables for Azure OpenAI access. Configure these in your system's environment:

**Required Environment Variables:**

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI resource URL | `https://my-resource.cognitiveservices.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Model deployment name | `gpt-4o-mini` |
| `AZURE_OPENAI_VERSION` | API version | `2025-03-01-preview` |
| `AZURE_OPENAI_API_KEY` | API key (falls back to `az login` if not set) | `your_api_key` |

**Optional Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `SPI_AGENT_ORGANIZATION` | `danielscholl-osdu` | GitHub organization to manage |
| `SPI_AGENT_REPOSITORIES` | `partition,legal,entitlements,schema,file,storage` | Comma-separated repository list |
| `GITLAB_URL` | `https://gitlab.com` | GitLab instance URL (for self-hosted instances) |
| `GITLAB_TOKEN` | *(none)* | GitLab personal access token (enables GitLab integration) |
| `GITLAB_DEFAULT_GROUP` | *(none)* | Default GitLab group/namespace for projects |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | *(none)* | Azure Application Insights for observability |
| `MAVEN_MCP_VERSION` | `mvn-mcp-server==2.3.0` | Override Maven MCP Server version |
| `SPI_AGENT_HOSTED_TOOLS_ENABLED` | `false` | Enable Microsoft Agent Framework hosted tools |
| `SPI_AGENT_HOSTED_TOOLS_MODE` | `complement` | Hosted tools mode (`complement`, `replace`, `fallback`) |

**Platform-specific setup:**

```bash
# macOS/Linux - Add to shell profile (~/.zshrc, ~/.bashrc, ~/.zshenv)
export AZURE_OPENAI_ENDPOINT="https://..."
export AZURE_OPENAI_API_KEY="your_api_key"

# Windows PowerShell - Add to profile ($PROFILE)
$env:AZURE_OPENAI_ENDPOINT="https://..."
$env:AZURE_OPENAI_API_KEY="your_api_key"

# Windows CMD - Set system environment variables via GUI or:
setx AZURE_OPENAI_ENDPOINT "https://..."
setx AZURE_OPENAI_API_KEY "your_api_key"
```


## Usage

Start the interactive chat interface:

```bash
spi
```

The agent provides conversational access to GitHub operations and Maven dependency management. Use natural language to manage issues, pull requests, workflows, and security scanning across your OSDU SPI repositories.

**Maven dependency scanning** is automatically available via the [Maven MCP Server](https://github.com/danielscholl/mvn-mcp-server) (v2.3.0, auto-installed). For security vulnerability scanning, install [Trivy](https://trivy.dev) (optional).

For command-line options:
```bash
spi --help
```

### GitLab Status Command

Get comprehensive status for GitLab repositories with provider-based filtering:

```bash
# Check single project with default providers (Azure,Core)
spi status --service partition --platform gitlab

# Check multiple projects with Azure provider only
spi status --service partition,legal --platform gitlab --provider Azure

# Check all projects with both Azure and Core providers
spi status --service all --platform gitlab --provider Azure,Core

# Check single project with custom provider
spi status --service storage --platform gitlab --provider GCP
```

**What It Shows:**
- Project Information: GitLab project exists, URL, last updated
- Open Issues: Filtered by provider labels (azure, core, etc.)
- Merge Requests: Filtered by provider labels, showing draft status
- Pipeline Runs: Recent CI/CD pipeline status (success, failed, running)
- Next Steps: Actionable items for failed pipelines, open MRs

**Provider Filtering:**
Provider filtering uses GitLab labels on issues and merge requests. When multiple providers are specified (e.g., `Azure,Core`), items with ANY of those labels are shown.

**Note:** GitLab labels are case-sensitive. Use capitalized names: `Azure`, `Core`, `GCP`, `AWS`


## Development & Testing

For local development and testing, clone the repository and install in editable mode:

```bash
# Clone the repository
git clone https://github.com/danielscholl-osdu/spi-agent.git
cd spi-agent

# Configure environment variables (optional - uses shell profile by default)
cp .env.example .env
# Edit .env with your values if preferred over shell profile

# Install in editable mode with dev dependencies
uv pip install -e ".[dev]" --prerelease=allow

# Run tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src/spi_agent --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_agent.py -v
```

**Note:** The `.env` file is provided for convenience during development. The agent still reads from `os.getenv()`, so ensure your shell environment variables are set or use a tool like `python-dotenv` if needed.


## Documentation

- [📖 Technical Specification](specs/init_spec.md) - Complete architecture, tools, implementation plan, and acceptance criteria


## License

MIT License - See LICENSE file for details

## Acknowledgments

- Built with [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- Powered by [Azure AI Foundry](https://azure.microsoft.com/en-us/products/ai-services/ai-studio)
- Workflow automation via [GitHub Copilot CLI](https://www.npmjs.com/package/@github/copilot)
