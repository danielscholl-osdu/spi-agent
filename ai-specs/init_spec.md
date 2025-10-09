# Feature: AI-Powered GitHub Management Agent for OSDU SPI Services

## Feature Description
An AI-powered CLI tool that provides natural language interface for comprehensive GitHub operations (Issues, Pull Requests, Workflows, Code Scanning) across OSDU SPI service repositories. Built with Microsoft Agent Framework, Azure OpenAI, and PyGithub, it combines conversational AI with 21 GitHub tools and optional Copilot-powered automation workflows for repository forking and status monitoring.

## User Story
As an **OSDU SPI maintainer**
I want to **manage GitHub repositories using natural language queries and automated workflows**
So that **I can efficiently handle issues, PRs, workflows, and security alerts without context-switching between tools and documentation**

## Problem Statement
Managing multiple OSDU SPI repositories requires:
- Context-switching between GitHub web UI, CLI tools, and documentation
- Remembering specific GitHub API syntax and parameters
- Manual tracking of repository initialization workflows
- Tedious status checks across multiple repositories
- Repetitive tasks like forking, configuring, and monitoring repositories

Developers spend significant time navigating GitHub interfaces instead of focusing on code.

## Solution Statement
A unified CLI agent that:
1. **Understands natural language** - "List open issues in partition" instead of complex API calls
2. **Maintains conversation context** - Follow-up questions work naturally
3. **Provides comprehensive GitHub operations** - 21 tools covering Issues, PRs, Workflows, and Security
4. **Automates repetitive workflows** - Fork and status commands with live progress tracking
5. **Delivers rich console output** - Beautiful formatting with Rich library
6. **Requires zero memorization** - Agent discovers and uses appropriate tools automatically

## Relevant Files
Use these files to implement the feature:

### Core Package Structure
- **`src/spi_agent/__init__.py`** - Package exports for SPIAgent class
- **`src/spi_agent/agent.py`** - Main SPIAgent class with Azure OpenAI integration and agent instructions (192 lines)
- **`src/spi_agent/config.py`** - Configuration management with environment variables and validation (77 lines)
- **`src/spi_agent/github_tools.py`** - 21 GitHub tool implementations using PyGithub (1597 lines)
- **`src/spi_agent/cli.py`** - Rich console CLI with interactive and one-shot modes (391 lines)

### Copilot Workflows (Optional)
- **`src/spi_agent/copilot/__init__.py`** - Enhanced copilot wrapper with live tracking (1394 lines)
- **`src/spi_agent/copilot/prompts/fork.md`** - Repository forking workflow definition
- **`src/spi_agent/copilot/prompts/status.md`** - Status gathering workflow definition

### Testing & Quality
- **`tests/test_agent.py`** - SPIAgent initialization and configuration tests
- **`tests/test_config.py`** - Configuration validation tests
- **`tests/test_github_tools.py`** - GitHub tools mocking and integration tests
- **`tests/conftest.py`** - Shared pytest fixtures

### Configuration & Deployment
- **`pyproject.toml`** - Package metadata, dependencies, console entry point
- **`.env.example`** - Environment variable template
- **`README.md`** - User-facing documentation and quick start
- **`LICENSE`** - MIT License

### New Files
None required - implementation is complete.

## Implementation Plan

### Phase 1: Foundation
- Set up project structure with src layout
- Configure pyproject.toml with dependencies
- Implement configuration management with Pydantic
- Integrate Microsoft Agent Framework
- Set up Azure OpenAI client with authentication fallback

### Phase 2: Core GitHub Tools
**Issues (7 tools):**
- `list_issues` - List with filtering (state, labels, assignees, limit)
- `get_issue` - Get full issue details
- `get_issue_comments` - Read all comments with pagination
- `create_issue` - Create with title, body, labels, assignees
- `update_issue` - Update any field including state
- `add_issue_comment` - Add markdown-formatted comments
- `search_issues` - Search across repositories

**Pull Requests (7 tools):**
- `list_pull_requests` - List with state/branch filtering
- `get_pull_request` - Get full PR details with merge readiness
- `get_pr_comments` - Read PR discussion comments
- `create_pull_request` - Create from branches with draft support
- `update_pull_request` - Update title/body/state/draft/labels
- `merge_pull_request` - Merge with method selection and safety checks
- `add_pr_comment` - Add comments to PR discussions

**Workflows (5 tools):**
- `list_workflows` - List available workflows
- `list_workflow_runs` - List runs with filtering
- `get_workflow_run` - Get run details with jobs summary
- `trigger_workflow` - Trigger workflow_dispatch with inputs
- `cancel_workflow_run` - Cancel running workflows

**Code Scanning (2 tools):**
- `list_code_scanning_alerts` - List security alerts with severity filtering
- `get_code_scanning_alert` - Get vulnerability details and remediation

### Phase 3: CLI & UX
- Implement Rich console interface with markdown rendering
- Create interactive chat mode with session memory
- Implement one-shot query mode
- Add copilot workflow integration (fork/status commands)
- Implement slash commands for workflows
- Create console entry point in pyproject.toml

### Phase 4: Copilot Workflows
- Build CopilotRunner with split-panel live tracking
- Implement StatusRunner with JSON extraction and validation
- Create fork.md workflow for repository initialization
- Create status.md workflow for GitHub data gathering
- Add auto-logging to logs/ directory
- Implement graceful shutdown and error handling

### Phase 5: Testing & Documentation
- Write unit tests for configuration
- Write integration tests for GitHub tools with mocking
- Create comprehensive README with installation instructions
- Document all 21 GitHub tools
- Create technical specifications
- Add copilot workflow documentation

## Step by Step Tasks

### Foundation Setup
- Initialize Python project with uv and pyproject.toml
- Configure setuptools with src layout
- Add dependencies: agent-framework, PyGithub, azure-identity, rich, pydantic, python-dotenv
- Create .env.example with all required variables
- Set up .gitignore for Python, logs, and environment files

### Configuration Management
- Create AgentConfig dataclass with environment variable loading
- Implement validation for required fields
- Add helper method get_repo_full_name for org/repo resolution
- Support both AZURE_OPENAI_VERSION and AZURE_OPENAI_API_VERSION
- Write tests for configuration validation

### GitHub Tools Implementation
- Create GitHubTools class with PyGithub client
- Implement private formatters: `_format_issue`, `_format_pr`, `_format_workflow`, `_format_workflow_run`, `_format_comment`, `_format_code_scanning_alert`
- Implement all 7 issue tools with consistent error handling
- Implement all 7 PR tools with merge safety checks
- Implement all 5 workflow tools with permission validation
- Implement 2 code scanning tools with URL parsing support
- Create create_github_tools factory function
- Write comprehensive tests with PyGithub mocking

### Agent Core
- Create SPIAgent class extending Microsoft Agent Framework
- Implement Azure OpenAI client initialization with credential fallback
- Write detailed agent instructions covering all 21 tools
- Add URL parsing intelligence for GitHub resources
- Implement async run() method
- Add run_interactive() for REPL mode

### CLI Interface
- Build Rich console interface with panels and markdown
- Implement interactive chat mode with continuous input loop
- Implement one-shot query mode with -p/--prompt flag
- Add quiet mode with -q/--quiet flag
- Integrate copilot workflow commands (fork/status subcommands)
- Handle slash commands within chat mode (/fork, /status, /help)
- Add help system and graceful exit handling
- Create main() entry point for console_scripts

### Copilot Workflows
- Build CopilotRunner with split-panel layout
- Implement ServiceTracker for real-time status updates
- Add smart output parsing to detect service progress
- Build StatusRunner with JSON extraction and Pydantic validation
- Create StatusTracker for data gathering progress
- Implement auto-logging with timestamps
- Add signal handling for graceful Ctrl+C shutdown
- Package prompt files with setuptools package-data

### Testing Strategy

#### Unit Tests
**Configuration Tests** (`tests/test_config.py`):
- Validate environment variable loading
- Test default value fallbacks
- Verify required field validation
- Test get_repo_full_name helper

**Agent Tests** (`tests/test_agent.py`):
- Test SPIAgent initialization with various configs
- Verify Azure OpenAI client creation
- Test credential fallback mechanism
- Validate agent instructions formatting

#### Integration Tests
**GitHub Tools Tests** (`tests/test_github_tools.py`):
- Mock PyGithub client for all 21 tools
- Test happy path for each tool
- Test 404 errors (resource not found)
- Test 403 errors (permission denied)
- Test 422 errors (validation failures)
- Test empty results handling
- Verify formatter outputs

#### Edge Cases
- Handle missing environment variables gracefully
- Handle expired GitHub tokens with clear messages
- Handle rate limiting with retry guidance
- Handle malformed repository names
- Handle network failures during API calls
- Handle missing prompt files for copilot workflows
- Handle JSON extraction failures in status command
- Handle workflow runs without started timestamps
- Truncate very long comment bodies (>1500 chars)
- Parse multiple GitHub URL formats for code scanning

## Acceptance Criteria

### Functional Requirements
- Agent responds to natural language queries about GitHub operations
- All 21 GitHub tools are accessible and functional
- Interactive chat mode maintains conversation context within session
- One-shot mode executes single queries and exits
- Fork command creates and initializes repositories with live tracking
- Status command gathers and displays comprehensive GitHub data
- Error messages are actionable and user-friendly
- URLs are always included in responses for reference
- Markdown formatting is preserved in console output

### Non-Functional Requirements
- Response time < 5s for simple queries (list, get)
- Response time < 15s for complex operations (search, create, fork)
- Works with both short (partition) and full (org/repo) repository names
- Supports Azure CLI authentication as fallback
- Console output is properly formatted with Rich library
- Package is installable via uv tool install
- All dependencies are properly declared and locked

### Quality Requirements
- Test coverage > 80% for core modules (agent, config, github_tools)
- All code passes mypy type checking (strict mode)
- Code formatted with black (line length 100)
- Linting passes with ruff
- No exposed secrets in code or documentation
- MIT license properly applied

## Validation Commands
Execute every command to validate the feature works correctly with zero regressions.

### Installation Validation
```bash
# Install package globally
uv tool install --prerelease=allow git+https://github.com/danielscholl-osdu/spi-agent.git

# Verify command is available
which spi-agent

# Check help output
spi-agent --help
```

### Configuration Validation
```bash
# Verify environment variables are loaded
export AZURE_OPENAI_ENDPOINT="https://test.cognitiveservices.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o"
export AZURE_OPENAI_VERSION="2024-12-01-preview"
export AZURE_OPENAI_API_KEY="test_key"
export GITHUB_TOKEN="ghp_test_token"

# Test configuration (should not error on import)
python -c "from spi_agent.config import AgentConfig; config = AgentConfig(); print(config.organization)"
```

### GitHub Tools Validation
```bash
# Run unit tests
cd spi-agent
uv pip install -e ".[dev]" --prerelease=allow
pytest tests/test_github_tools.py -v

# Run all tests
pytest tests/ -v --cov=spi_agent --cov-report=term-missing

# Type check
mypy src/spi_agent/ --strict

# Lint check
ruff check src/ tests/

# Format check
black --check src/ tests/
```

### CLI Validation
```bash
# Test interactive mode (requires valid credentials)
spi-agent
# Type: help
# Type: exit

# Test one-shot query
spi-agent -p "List issues in partition"

# Test quiet mode
spi-agent -q -p "How many repositories?"

# Test fork command (requires GitHub Copilot CLI)
spi-agent fork --services partition --branch main

# Test status command
spi-agent status --services partition
```

### Integration Validation
```bash
# Test with real GitHub API (requires valid GITHUB_TOKEN)
spi-agent -p "List all open issues in partition"
spi-agent -p "Show me issue #2 in partition"
spi-agent -p "List workflows in legal"
spi-agent -p "List code scanning alerts in partition"
```

### Package Validation
```bash
# Build distribution
uv build

# Install from dist
uv tool install dist/spi_agent-0.1.0-py3-none-any.whl

# Verify entry point
spi-agent --help

# Uninstall
uv tool uninstall spi-agent
```

## Notes

### Technology Stack Rationale
- **Microsoft Agent Framework (>=1.0.0b251001)**: Provides agent orchestration, LLM integration, and built-in tool calling support
- **Azure OpenAI**: Reliable LLM backend with function calling support (gpt-4o, gpt-5-mini compatible)
- **PyGithub (>=2.8.1)**: Mature Python library for GitHub API v3 with comprehensive coverage
- **Rich (>=14.1.0)**: Beautiful console UI with markdown rendering, panels, and progress indicators
- **Pydantic (>=2.11.10)**: Data validation and settings management with type safety
- **Python-dotenv (>=1.1.1)**: Environment variable management from .env files

### Design Decisions
1. **Single GitHubTools class**: Grouped methods by domain (Issues/PRs/Workflows) instead of separate classes for simplicity
2. **String return types**: All tools return formatted strings for LLM consumption rather than structured data
3. **Thread-based memory**: Conversation context within session only, no persistent memory across restarts
4. **Optional copilot**: Copilot workflows are optional features that require GitHub Copilot CLI
5. **Unified CLI**: Single `spi-agent` command handles all modes (chat, query, fork, status)

### Future Enhancements
- [ ] Add web search capability for documentation lookup
- [ ] Implement persistent memory with vector database
- [ ] Add repository management tools (labels, milestones, projects)
- [ ] Support multiple organizations
- [ ] Add webhook integration for real-time updates
- [ ] Create web UI for non-terminal usage
- [ ] Add Slack/Teams integration
- [ ] Implement CI/CD automation workflows

### Known Limitations
1. No persistent memory across sessions (by design)
2. Single organization support only
3. Rate limited by GitHub API (5000 requests/hour authenticated)
4. Copilot workflows require GitHub Copilot CLI installation
5. Fork command requires repository write permissions
6. Code scanning tools require security_events scope on GitHub token

### Troubleshooting
**"Functions are not supported with <model>"**
- Solution: Use gpt-5-mini, gpt-4o, or gpt-4o-mini deployment

**"Bad credentials" from GitHub**
- Solution: Verify GITHUB_TOKEN is valid and has not expired

**"Copilot module not available"**
- Solution: Copilot workflows are optional; basic agent works without them

**"Resource not found / Deployment not found"**
- Solution: Verify AZURE_OPENAI_DEPLOYMENT_NAME and endpoint are correct
