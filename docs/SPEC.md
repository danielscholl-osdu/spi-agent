# SPI Agent Specification

## Overview

SPI Agent is a unified CLI tool for managing OSDU SPI services, combining:
- **Natural language GitHub issue management** via Microsoft Agent Framework
- **Interactive chat interface** with conversation memory
- **Rich console UI** with beautiful formatting

## Architecture

### Core Components

```
spi-agent/
├── spi.py                    # Unified CLI entry point
├── src/spi_agent/
│   ├── agent.py             # Main SPIAgent class
│   ├── config.py            # Configuration management
│   ├── github_tools.py      # GitHub API tool implementations
│   └── __init__.py
├── tests/                    # Test suite
├── docs/                     # Documentation
└── pyproject.toml           # Dependencies and metadata
```

### Technology Stack

- **Microsoft Agent Framework** - Agent orchestration and LLM integration
- **Azure OpenAI** - Language model (gpt-5-mini or compatible)
- **PyGithub** - GitHub API interactions
- **Rich** - Beautiful console UI
- **Pydantic** - Configuration and data validation

## Usage Modes

### 1. Interactive Chat Mode (Default)

**Command:**
```bash
uv run --prerelease=allow spi.py
```

**Features:**
- Natural language conversations about GitHub issues
- Thread-based memory (remembers within session)
- Rich UI with markdown formatting, panels, and status indicators
- Type `help` for available commands
- Type `exit` to quit

**Example Session:**
```
You: How many open issues are in partition?
Agent: There is 1 open issue in danielscholl-osdu/partition...

You: Tell me more about it
Agent: [Remembers context, provides details about issue #2]

You: exit
```

### 2. One-Shot Query Mode

**Command:**
```bash
uv run --prerelease=allow spi.py -p "Your query here"
```

**Examples:**
```bash
spi.py -p "List issues in partition"
spi.py -p "Show me issues labeled bug in legal"
spi.py -p "Search for CodeQL across repositories"
spi.py -q -p "How many issues?"  # Quiet mode
```

## GitHub Tools

The agent has access to **21 GitHub tools** across four domains:

### Issues (7 tools)

#### 1. List Issues
Lists issues from a repository with optional filtering.

**Examples:**
- "List open issues in partition"
- "Show me closed bugs in legal"

#### 2. Get Issue
Retrieves detailed information about a specific issue.

**Examples:**
- "Tell me about issue #2 in partition"
- "Show details for issue #5"

#### 3. Get Issue Comments
Reads all comments on an issue.

**Examples:**
- "Show me comments on issue #5"
- "What are people saying about issue #2?"

#### 4. Create Issue
Creates a new issue in a repository.

**Examples:**
- "Create an issue in partition: Fix authentication bug"
- "Create a bug report in legal with label security"

#### 5. Update Issue
Updates an existing issue (including closing).

**Examples:**
- "Close issue #2 in partition"
- "Add label 'bug' to issue #3"

#### 6. Add Issue Comment
Adds a comment to an existing issue.

**Examples:**
- "Add comment to issue #2: This is fixed in v1.2"
- "Comment on issue #5: Needs investigation"

#### 7. Search Issues
Searches for issues across repositories.

**Examples:**
- "Search for CodeQL across all repositories"
- "Find issues mentioning authentication"

### Pull Requests (7 tools)

#### 8. List Pull Requests
Lists PRs in a repository with filtering.

**Examples:**
- "List open PRs in partition"
- "Show me all PRs in legal"

#### 9. Get Pull Request
Retrieves detailed PR information including merge readiness.

**Examples:**
- "Show me PR #5"
- "Get details for pull request #10 in partition"

#### 10. Get PR Comments
Reads discussion comments on a PR.

**Examples:**
- "What are people saying about PR #5?"
- "Show comments on pull request #10"

#### 11. Create Pull Request
Creates a new pull request from branches.

**Examples:**
- "Create a PR from feature/auth to main in partition"
- "Open a pull request for my changes"

#### 12. Update Pull Request
Updates PR metadata (title, body, state, draft status).

**Examples:**
- "Close PR #5"
- "Mark PR #10 as ready for review"

#### 13. Merge Pull Request
Merges a pull request with specified method.

**Examples:**
- "Merge PR #5 using squash"
- "Merge pull request #10"

#### 14. Add PR Comment
Adds a comment to PR discussion.

**Examples:**
- "Comment on PR #5: Looks good to me"
- "Add comment to pull request #10: Needs tests"

### Workflows & Actions (5 tools)

#### 15. List Workflows
Lists available workflows in a repository.

**Examples:**
- "What workflows are in partition?"
- "Show me all workflows in legal"

#### 16. List Workflow Runs
Lists recent workflow runs with filtering.

**Examples:**
- "Show me recent workflow runs"
- "List failed runs in partition"

#### 17. Get Workflow Run
Gets detailed information about a specific workflow run.

**Examples:**
- "Show me workflow run #123"
- "Get details for run #456"

#### 18. Trigger Workflow
Manually triggers a workflow (workflow_dispatch).

**Examples:**
- "Trigger the build workflow on main"
- "Run the release workflow"

#### 19. Cancel Workflow Run
Cancels a running or queued workflow.

**Examples:**
- "Cancel workflow run #123"
- "Stop run #456"

### Code Scanning (2 tools)

#### 20. List Code Scanning Alerts
Lists code scanning alerts in a repository with filtering.

**Examples:**
- "List code scanning alerts in partition"
- "Show me critical security alerts in legal"
- "List open code scanning alerts in entitlements"

#### 21. Get Code Scanning Alert
Retrieves detailed information about a specific code scanning alert.

**Examples:**
- "Tell me about code scanning alert #5 in partition"
- "Show details for security alert #3"
- "Look at https://github.com/danielscholl-osdu/partition/security/code-scanning/5"

**What you get:**
- Alert severity (critical, high, medium, low)
- Rule information (ID, name, description)
- Affected file path and line numbers
- Security tags and CWE identifiers
- Tool information (e.g., CodeQL version)
- Remediation guidance
- Dismissal information (if dismissed)

**URL Handling:**
The agent can intelligently parse GitHub URLs for code scanning alerts:
- `https://github.com/org/repo/security/code-scanning/5` → extracts alert #5

## Configuration

### Environment Variables

**Required:**
```bash
# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT="https://your-resource.cognitiveservices.azure.com/"
AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5-mini"
AZURE_OPENAI_VERSION="2025-03-01-preview"  # or AZURE_OPENAI_API_VERSION
AZURE_OPENAI_API_KEY="your_key"

# GitHub Configuration
GITHUB_TOKEN="ghp_your_token_here"
```

**Optional:**
```bash
# SPI Agent Configuration
SPI_AGENT_ORGANIZATION="danielscholl-osdu"
SPI_AGENT_REPOSITORIES="partition,legal,entitlements,schema,file,storage"
```

### Configuration File

Optionally create `.env` file in the spi-agent directory:

```bash
cp .env.example .env
# Edit .env with your values
```

**Note:** Environment variables in shell take precedence over `.env` file.

## Agent Instructions

The agent is instructed to:

1. **Understand repository references** - Accept both short names ("partition") and full names ("org/repo")
2. **Provide helpful responses** - Be concise, proactive, and suggest related actions
3. **Format properly** - Use markdown, provide URLs, format lists clearly
4. **Confirm actions** - When creating/updating issues, confirm what changed
5. **Handle errors gracefully** - Provide clear error messages with guidance

## Conversation Memory

**Thread-Based Memory (Built-in):**
- Remembers full conversation within a session
- Maintains context across multiple questions
- Allows follow-up questions without repeating context
- Resets when you exit and restart

**No Persistent Memory:**
- Agent forgets previous sessions when restarted
- Each session starts fresh
- Suitable for most use cases

## Error Handling

### Common Errors

**1. Authentication Failed**
```
Error: Bad credentials
```
**Solution:** Check GITHUB_TOKEN is valid and has repo access

**2. Repository Not Found**
```
Error: Repository not found
```
**Solution:** Verify repository exists and GITHUB_TOKEN has access

**3. Azure OpenAI Error**
```
Error: Resource not found / Deployment not found
```
**Solution:** Verify AZURE_OPENAI_DEPLOYMENT_NAME and endpoint are correct

**4. Functions Not Supported**
```
Error: Functions are not supported with <model>
```
**Solution:** Use gpt-5-mini, gpt-4o, or gpt-4o-mini deployment

## Development

### Running Tests

```bash
cd spi-agent

# Install with dev dependencies
uv pip install -e ".[dev]" --prerelease=allow

# Run tests
pytest

# Run with coverage
pytest --cov=spi_agent --cov-report=html
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## Deployment

### As a Package

```bash
# Install from source
uv pip install -e . --prerelease=allow

# Use as library
from spi_agent import SPIAgent
agent = SPIAgent()
result = await agent.run("List issues in partition")
```

### As a CLI Tool

```bash
# Run directly with uv
uv run --prerelease=allow spi.py

# Or create executable
chmod +x spi.py
./spi.py
```

## Extensibility

### Adding New GitHub Tools

1. Add function to `src/spi_agent/github_tools.py`
2. Use `typing.Annotated` and `pydantic.Field` for parameter descriptions
3. Return clear, formatted strings
4. Add to `create_github_tools()` function

**Example:**
```python
def get_pull_requests(
    repository: Annotated[str, Field(description="Repository name")],
    state: Annotated[str, Field(description="State: open, closed, all")] = "open",
) -> str:
    """List pull requests in a repository."""
    # Implementation
    return formatted_result
```

### Customizing Agent Instructions

Edit `src/spi_agent/agent.py` to modify the `self.instructions` string.

## Security Considerations

- **API Keys**: Never commit .env files or expose tokens
- **Token Permissions**: GITHUB_TOKEN requires `repo` scope minimum
- **Rate Limiting**: GitHub API has rate limits (5000/hour authenticated)
- **Input Validation**: All user inputs are validated before GitHub API calls

## Limitations

1. **No persistent memory** across sessions (thread-based only)
2. **Read-only operations preferred** - Creating/updating requires careful review
3. **Single organization** - Configured to work with one org at a time
4. **Rate limits** - Subject to GitHub and Azure OpenAI rate limits

## Future Enhancements

### Planned
- Local file-based memory persistence
- Pull request management capabilities
- Repository management (labels, milestones)
- Webhook integration for real-time updates
- Multi-organization support

### Under Consideration
- Web UI for non-terminal usage
- Slack/Teams integration
- CI/CD integration
- Analytics and reporting

## Version History

### 0.1.0 (Current)
- Initial release
- Interactive chat and one-shot query modes
- Six core GitHub tools (list, get, create, update, comment, search)
- Thread-based conversation memory
- Rich console UI
- Configuration via environment variables
- Comprehensive test suite

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or contributions, please open an issue in the GitHub repository.
