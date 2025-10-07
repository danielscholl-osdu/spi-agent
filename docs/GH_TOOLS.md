# GitHub Tools Design Specification

## Executive Summary

This document defines the optimal design for `github_tools.py` to support comprehensive GitHub operations across **Issues**, **Pull Requests**, and **GitHub Actions/Workflows**. The design balances LLM usability, developer maintainability, and API efficiency.

---

## Design Review Highlights (2025-02-15)

- ✅ Architectural direction (single `GitHubTools` class with grouped methods) remains valid; no refactor required.
- ✅ Phase 2 pull-request scope is intentionally limited to core metadata; advanced review/check aggregation moved to a follow-on enhancement.
- ✅ Workflow dispatch inputs now require JSON strings only, aligning with GitHub's API requirements and simplifying validation.
- ✅ Branch handling is explicit—callers provide `branch` or `owner:branch`; spec documents helpful error messaging instead of auto-qualifying.
- ✅ Rate-limit guidance now triggers only when GitHub returns a 403 mentioning the limit, reducing unnecessary API calls.
- ⚠️ `list_pull_requests` example output previously contradicted the default `state="open"` filter. Examples now explicitly note when `state="all"` is used.
- ✅ `get_issue_comments` remains the top priority gap for Phase 1 rollout, and helper responsibilities stay focused on LLM-friendly responses without redundant API calls.

---

## Design Principles

### 1. **LLM-First Design**
- All tools return formatted strings optimized for LLM consumption and user presentation
- Use `typing.Annotated` + `pydantic.Field` for rich parameter descriptions
- Tool names are intuitive and action-oriented (verbs + nouns)
- Responses include URLs for user reference

### 2. **Consistency**
- Uniform naming patterns within each domain (list, get, create, update, add_comment)
- Consistent return format (headers, bullets, URLs, status indicators)
- Standardized error handling across all methods

### 3. **Appropriate Granularity**
- Each tool represents a **single logical action** an LLM would naturally take
- Avoid over-fragmentation (e.g., separate "close_issue" when update_issue handles it)
- Avoid under-fragmentation (don't combine unrelated operations)

### 4. **Type Safety & Testing**
- Full type hints on all methods (mypy strict mode compatible)
- Mockable dependencies for unit testing
- Helper methods for formatting to reduce duplication

### 5. **API Efficiency**
- Minimize redundant GitHub API calls
- Use pagination parameters effectively
- Cache client connections

---

## Architectural Decision: Hybrid Approach

**Selected Pattern:** Single `GitHubTools` class with logical method groupings

```python
class GitHubTools:
    """GitHub operations toolkit using PyGithub."""

    # ============ ISSUES ============
    def list_issues(...)
    def get_issue(...)
    def get_issue_comments(...)
    def create_issue(...)
    def update_issue(...)
    def add_issue_comment(...)
    def search_issues(...)

    # ========= PULL REQUESTS =========
    def list_pull_requests(...)
    def get_pull_request(...)
    def get_pr_comments(...)
    def create_pull_request(...)
    def update_pull_request(...)
    def merge_pull_request(...)
    def add_pr_comment(...)

    # ====== WORKFLOWS/ACTIONS ======
    def list_workflows(...)
    def list_workflow_runs(...)
    def get_workflow_run(...)
    def trigger_workflow(...)
    def cancel_workflow_run(...)

    # ======== FORMATTERS ========
    def _format_issue(...)
    def _format_pr(...)
    def _format_workflow(...)
    def _format_workflow_run(...)
```

**Rationale:**
- ✅ Clear separation via comments and naming
- ✅ Shared infrastructure (GitHub client, config)
- ✅ Manageable class size (25-30 public methods)
- ✅ Easy to test individual domains
- ✅ Simple initialization and tool registration

**Rejected Alternatives:**
- ❌ Separate classes per domain: Over-engineered for current scope, complicates initialization
- ❌ Monolithic without grouping: Hard to navigate, unclear responsibilities

---

## Tool Inventory

### Issues (7 tools)

#### 1. `list_issues` ✅ Keep Current
**Purpose:** Explore issues with filtering
**Parameters:**
- `repo: str` - Repository name (short or full)
- `state: str = "open"` - State filter (open/closed/all)
- `labels: Optional[str] = None` - Comma-separated labels
- `assignee: Optional[str] = None` - Assignee username
- `limit: int = 30` - Max results

**Returns:** Formatted list with number, title, labels, state, author, URL

---

#### 2. `get_issue` ✅ Keep Current
**Purpose:** Get full details for specific issue
**Parameters:**
- `repo: str` - Repository name
- `issue_number: int` - Issue number

**Returns:** Full issue details with title, body, labels, assignees, timestamps, URL

---

#### 3. `get_issue_comments` 🆕 NEW
**Purpose:** Read all comments on an issue (currently missing)
**Parameters:**
- `repo: str` - Repository name
- `issue_number: int` - Issue number
- `limit: int = 50` - Max comments to retrieve

**Returns:**
```
Comments on issue #5 in danielscholl-osdu/partition:

Comment #1 by danielscholl (2025-01-15T10:30:00Z):
  This looks like a duplicate of #3. Let me investigate.
  URL: https://github.com/.../issuecomment-123

Comment #2 by github-actions[bot] (2025-01-15T11:45:00Z):
  CodeQL scan completed successfully.
  URL: https://github.com/.../issuecomment-124

Total: 2 comments
```

**Implementation:**
```python
def get_issue_comments(
    self,
    repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
    issue_number: Annotated[int, Field(description="Issue number")],
    limit: Annotated[int, Field(description="Maximum number of comments")] = 50,
) -> str:
    """
    Get comments from an issue.

    Returns formatted string with comment list.
    """
```

**Note:** Very long comment bodies are truncated with a trailing `"… (comment truncated)"` marker to keep responses readable for the agent.

---

#### 4. `create_issue` ✅ Keep Current
**Purpose:** Create new issue
**Parameters:**
- `repo: str`
- `title: str`
- `body: Optional[str] = None`
- `labels: Optional[str] = None`
- `assignees: Optional[str] = None`

**Returns:** Confirmation with issue number and URL

---

#### 5. `update_issue` ✅ Keep Current
**Purpose:** Update any issue field (title, body, state, labels, assignees)
**Parameters:**
- `repo: str`
- `issue_number: int`
- `title: Optional[str] = None`
- `body: Optional[str] = None`
- `state: Optional[str] = None` - "open" or "closed"
- `labels: Optional[str] = None`
- `assignees: Optional[str] = None`

**Returns:** Confirmation with updated fields

**Note:** This handles closing issues via `state="closed"`. No need for separate `close_issue` tool.

---

#### 6. `add_issue_comment` ✅ Keep Current
**Purpose:** Add comment to issue
**Parameters:**
- `repo: str`
- `issue_number: int`
- `comment: str` - Markdown supported

**Returns:** Confirmation with comment URL

---

#### 7. `search_issues` ✅ Keep Current
**Purpose:** Search across repositories
**Parameters:**
- `query: str` - Search terms
- `repos: Optional[str] = None` - Specific repos (searches all if None)
- `limit: int = 30`

**Returns:** Cross-repo search results with repo names

---

### Pull Requests (7 tools)

#### 8. `list_pull_requests` 🆕 NEW
**Purpose:** List PRs in a repository
**Parameters:**
- `repo: str` - Repository name (short or full)
- `state: str = "open"` - State filter (`open`/`closed`/`all`)
- `base_branch: Optional[str] = None` - Filter by base branch (e.g., `main`, `release/1.0`)
- `head_branch: Optional[str] = None` - Filter by head branch; accept `feature/auth` or fully qualified `user:feature/auth`
- `limit: int = 30` - Maximum PRs to return after filtering

**Returns:**
```
Found 3 pull requests in danielscholl-osdu/partition (state=all):

#5: feat: Add authentication layer [open]
  Author: danielscholl | Base: main ← Head: feature/auth
  State: open | Draft: no | Mergeable: clean
  Conversation: 5 comments | Files changed: 12 | +456/-123
  Created: 2025-01-15T10:00:00Z
  URL: https://github.com/danielscholl-osdu/partition/pull/5

#4: fix: Memory leak in cache [merged]
  Author: contributor | Base: main ← Head: fix/cache-leak
  State: merged | Draft: no
  Conversation: 3 comments | Files changed: 4 | +98/-12
  Merged: 2025-01-14T15:30:00Z
  URL: https://github.com/danielscholl-osdu/partition/pull/4
```

**Notes:**
- Default `state="open"` only surfaces active PRs; include `state="all"` (as shown above) to surface closed/merged PRs.
- Implementation should reuse existing `_format_pr` helper and rely on fields already available on the `PullRequest` object (counts, mergeability, timestamps).

---

#### 9. `get_pull_request` 🆕 NEW
**Purpose:** Get full PR details
**Parameters:**
- `repo: str`
- `pr_number: int`

**Returns:**
```
Pull Request #5 in danielscholl-osdu/partition

Title: feat: Add authentication layer
State: open
Author: danielscholl
Base: main ← Head: feature/auth
Created: 2025-01-15T10:00:00Z
Updated: 2025-01-15T14:30:00Z

Changes:
  📝 Files changed: 12
  ➕ Additions: 456 lines
  ➖ Deletions: 123 lines
  💬 Conversation: 5 general comments | 2 review comments

Merge Readiness:
  Mergeable: yes (clean)
  Draft: no

Description:
This PR adds JWT-based authentication...

URL: https://github.com/danielscholl-osdu/partition/pull/5
```

**Implementation Notes:**
- Phase 2 scope: rely only on attributes already present on the `PullRequest` object (`pull.state`, `pull.draft`, `pull.mergeable`, counts, etc.) to avoid additional API calls.
- Derive conversation counts via `pull.comments` (issue comments) and `pull.review_comments` (inline review comments); surface the high-level counts only.
- File/change metadata comes from `pull.additions`, `pull.deletions`, and `pull.changed_files` without fetching full diffs.
- Future enhancement: aggregate review decisions and CI status signals before surfacing them to the agent.

---

#### 10. `get_pr_comments` 🆕 NEW
**Purpose:** Get discussion comments on PR (issue comments, not review comments)
**Parameters:**
- `repo: str`
- `pr_number: int`
- `limit: int = 50`

**Returns:** Similar format to `get_issue_comments`

**Implementation Notes:**
- Retrieve comments via `pull.as_issue().get_comments()` to stay aligned with GitHub's issue discussion model.
- Preserve chronological order and stop once `limit` is reached; annotate when additional comments exist.
- Reuse `_format_comment` helper (with optional truncation for very long bodies) to keep output consistent.

---

#### 11. `create_pull_request` 🆕 NEW
**Purpose:** Create new pull request
**Parameters:**
- `repo: str`
- `title: str`
- `body: Optional[str] = None` - PR description
- `head_branch: str` - Source branch
- `base_branch: str = "main"` - Target branch
- `draft: bool = False` - Create as draft PR
- `maintainer_can_modify: bool = True` - Allow maintainers to push to the source branch (optional toggle)

**Returns:** Confirmation with PR number and URL

**Implementation Notes:**
- Expect callers to provide `head_branch` exactly as GitHub expects (e.g., `feature/auth` for same-repo branches or `username:feature/auth` for forks).
- When GitHub returns a "branch not found" validation error, transform it into actionable guidance explaining the two accepted formats.
- Validate that both base and head branches exist before attempting creation so errors are descriptive rather than surfacing raw GitHub exceptions.
- When `draft=True`, ensure subsequent updates (e.g., `update_pull_request`) can set `draft=False` to ready the PR for review.

---

#### 12. `update_pull_request` 🆕 NEW
**Purpose:** Update PR metadata
**Parameters:**
- `repo: str`
- `pr_number: int`
- `title: Optional[str] = None`
- `body: Optional[str] = None`
- `state: Optional[str] = None` - `"open"` or `"closed"`
- `draft: Optional[bool] = None` - Transition between draft and ready-for-review
- `base_branch: Optional[str] = None` - Update the target branch (rare, but supported)
- `labels: Optional[str] = None` - Comma-separated labels (applied via underlying issue)
- `assignees: Optional[str] = None` - Comma-separated assignees (applied via underlying issue)

**Returns:** Confirmation with updated fields

**Implementation Notes:**
- Use `pull.edit(...)` for title/body/state/draft/base updates.
- When labels or assignees are provided, call `pull.as_issue().edit(labels=..., assignees=...)` in a separate step to keep responsibilities clear.
- Reject invalid combinations (e.g., attempting to open a merged PR) with descriptive messages rather than forwarding GitHub's validation error directly.

---

#### 13. `merge_pull_request` 🆕 NEW
**Purpose:** Merge a pull request
**Parameters:**
- `repo: str`
- `pr_number: int`
- `merge_method: str = "merge"` - Merge method (merge/squash/rebase)
- `commit_title: Optional[str] = None` - Custom merge commit title
- `commit_message: Optional[str] = None` - Custom merge commit message
- `expected_head_sha: Optional[str] = None` - Optional SHA guard to prevent merging stale heads

**Returns:**
```
✓ Merged pull request #5 in danielscholl-osdu/partition
Method: squash
Commit SHA: abc123def456
URL: https://github.com/danielscholl-osdu/partition/pull/5
```

**Safety:** Should check `pull.mergeable` and `pull.mergeable_state` before attempting the merge, surface merge blockers (e.g., failing checks, conflicts) clearly, and honour `expected_head_sha` to avoid race conditions.

**Notes:**
- `expected_head_sha` is an advanced safety guard. Most conversational workflows can omit it; when supplied, validate against the PR's current head before merging.

---

#### 14. `add_pr_comment` 🆕 NEW
**Purpose:** Add comment to PR discussion
**Parameters:**
- `repo: str`
- `pr_number: int`
- `comment: str` - Markdown supported

**Returns:** Confirmation with comment URL

**Implementation Notes:**
- Use `pull.create_issue_comment(comment)` so the message appears in the PR conversation tab.
- Guard against empty comments post-whitespace-trim and surface GitHub validation errors (e.g., repository permissions) as user-friendly text.

---

### GitHub Actions/Workflows (5 tools)

#### 15. `list_workflows` 🆕 NEW
**Purpose:** List available workflows in repository
**Parameters:**
- `repo: str`
- `limit: int = 50`

**Returns:**
```
Workflows in danielscholl-osdu/partition:

1. Build and Test (build.yml)
   ID: 12345678 | State: active
   Path: .github/workflows/build.yml

2. CodeQL Analysis (codeql.yml)
   ID: 12345679 | State: active
   Path: .github/workflows/codeql.yml

3. Release Management (release.yml)
   ID: 12345680 | State: active
   Path: .github/workflows/release.yml

Total: 3 workflows
```

**Implementation Notes:**
- Fetch workflows via `repo.get_workflows()` and cap the list to `limit` entries while preserving GitHub's default ordering (alphabetical by name).
- Surface both active and disabled workflows; include an indicator (e.g., `state: disabled_manually`) so the agent can explain why a workflow may not run.

---

#### 16. `list_workflow_runs` 🆕 NEW
**Purpose:** List recent workflow runs
**Parameters:**
- `repo: str`
- `workflow_name_or_id: Optional[str] = None` - Filter by specific workflow
- `status: Optional[str] = None` - Filter by status (completed, in_progress, queued)
- `branch: Optional[str] = None` - Filter by branch
- `limit: int = 30`

**Returns:**
```
Recent workflow runs in danielscholl-osdu/partition:

Build and Test - Run #123
  Status: ✓ completed (success)
  Branch: main | Commit: abc123d
  Triggered by: push
  Started: 2025-01-15T10:00:00Z | Duration: 3m 45s
  URL: https://github.com/danielscholl-osdu/partition/actions/runs/123

CodeQL Analysis - Run #124
  Status: ⏳ in_progress
  Branch: main | Commit: abc123d
  Triggered by: schedule
  Started: 2025-01-15T10:05:00Z | Duration: running
  URL: https://github.com/danielscholl-osdu/partition/actions/runs/124

Build and Test - Run #122
  Status: ✗ completed (failure)
  Branch: feature/auth | Commit: def456a
  Triggered by: pull_request
  Started: 2025-01-15T09:30:00Z | Duration: 2m 15s
  URL: https://github.com/danielscholl-osdu/partition/actions/runs/122

Total: 3 runs (showing most recent)
```

**Implementation Notes:**
- Support both numeric IDs and workflow file names when resolving `workflow_name_or_id`. When a name is supplied, look up the workflow collection first to obtain the correct ID.
- Apply filters via GitHub's API when possible (`workflow_runs = workflow.get_runs()`), then perform any remaining filtering client-side before slicing to `limit`.
- Avoid fetching job details within this method; job summaries belong in `get_workflow_run` to keep this listing lightweight.

---

#### 17. `get_workflow_run` 🆕 NEW
**Purpose:** Get detailed info about specific workflow run
**Parameters:**
- `repo: str`
- `run_id: int` - Workflow run ID

**Returns:**
```
Workflow Run #123 in danielscholl-osdu/partition

Workflow: Build and Test (build.yml)
Status: ✓ completed
Conclusion: success
Branch: main
Commit: abc123d - "feat: Add authentication layer"
Triggered by: push
Actor: danielscholl

Timing:
  Created: 2025-01-15T10:00:00Z
  Started: 2025-01-15T10:00:15Z
  Completed: 2025-01-15T10:03:45Z
  Duration: 3m 30s

Jobs (3):
  ✓ lint - completed (success) - 45s
  ✓ test - completed (success) - 2m 15s
  ✓ build - completed (success) - 1m 30s

Logs URL: https://github.com/danielscholl-osdu/partition/actions/runs/123
Run URL: https://github.com/danielscholl-osdu/partition/actions/runs/123
```

**Note:** Include job-level summary but not step-level details (too verbose)

**Implementation Notes:**
- Retrieve job data using `run.get_jobs()` and summarise the first 10 jobs; if more exist, append a note indicating additional jobs were omitted for brevity.
- Guard against `None` timestamps (GitHub may omit `run.run_started_at` for queued runs) by substituting `"Not started"`.
- Provide both the run URL and logs URL (identical today but may diverge if GitHub introduces deep links later).

---

#### 18. `trigger_workflow` 🆕 NEW
**Purpose:** Manually trigger a workflow (workflow_dispatch)
**Parameters:**
- `repo: str`
- `workflow_name_or_id: str` - Workflow filename or ID
- `ref: str = "main"` - Branch/tag/SHA to run workflow on
- `inputs: Optional[str] = None` - JSON string of workflow inputs (if workflow accepts inputs)

**Returns:**
```
✓ Triggered workflow "Build and Test" in danielscholl-osdu/partition
Branch: main
Status: Workflow dispatch event created
Note: Check workflow runs list to see execution

Workflow URL: https://github.com/danielscholl-osdu/partition/actions/workflows/build.yml
```

**Constraints:**
- Workflow must have `workflow_dispatch` trigger configured
- User must have write permissions to repository
- Inputs must be valid JSON that matches the workflow's declared inputs (strings only; boolean/number values should be passed as strings to satisfy GitHub's API)

**Error Cases:**
- Workflow not found
- Workflow doesn't support workflow_dispatch
- Invalid inputs format
- Permission denied

**Implementation Notes:**
- Parse `inputs` strictly as JSON via `json.loads`; return a clear validation message if parsing fails or any value is not a string.
- Use `workflow.create_dispatch(ref=ref, inputs=parsed_inputs)`; if a filename was supplied, resolve via `repo.get_workflow("file.yml")`.
- After dispatch, no run ID is returned—remind users to watch `list_workflow_runs` for confirmation.

---

#### 19. `cancel_workflow_run` 🆕 NEW
**Purpose:** Cancel a running workflow
**Parameters:**
- `repo: str`
- `run_id: int` - Workflow run ID

**Returns:**
```
✓ Cancelled workflow run #124 in danielscholl-osdu/partition
Workflow: CodeQL Analysis
Previous status: in_progress
URL: https://github.com/danielscholl-osdu/partition/actions/runs/124
```

**Constraints:**
- Can only cancel runs in progress or queued
- User must have write permissions

**Implementation Notes:**
- Verify the run status before invoking `run.cancel()`; if GitHub reports `completed`, respond with a helpful message instead of attempting cancellation.
- Capture and surface GitHub's "job already completed" validation errors so users know why cancellation failed.

---

## Formatting Helpers

### Private Methods for Consistent Output

```python
def _format_issue(self, issue: Any) -> Dict[str, Any]:
    """Format GitHub issue to dict."""
    # Current implementation - keep as is

def _format_pr(self, pr: Any) -> Dict[str, Any]:
    """Format GitHub pull request to dict."""
    return {
        "number": pr.number,
        "title": pr.title,
        "body": pr.body or "",
        "state": pr.state,
        "draft": pr.draft,
        "merged": pr.merged,
        "mergeable": pr.mergeable,
        "base_ref": pr.base.ref,
        "head_ref": pr.head.ref,
        "labels": [label.name for label in pr.labels],
        "assignees": [assignee.login for assignee in pr.assignees],
        "created_at": pr.created_at.isoformat(),
        "updated_at": pr.updated_at.isoformat(),
        "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
        "html_url": pr.html_url,
        "comments_count": pr.comments,
        "commits_count": pr.commits,
        "changed_files": pr.changed_files,
        "additions": pr.additions,
        "deletions": pr.deletions,
        "author": pr.user.login if pr.user else "unknown",
    }

def _format_workflow(self, workflow: Any) -> Dict[str, Any]:
    """Format GitHub workflow to dict."""
    return {
        "id": workflow.id,
        "name": workflow.name,
        "path": workflow.path,
        "state": workflow.state,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
        "html_url": workflow.html_url,
    }

def _format_workflow_run(self, run: Any) -> Dict[str, Any]:
    """Format GitHub workflow run to dict."""
    return {
        "id": run.id,
        "name": run.name,
        "workflow_id": run.workflow_id,
        "status": run.status,  # queued, in_progress, completed
        "conclusion": run.conclusion,  # success, failure, cancelled, skipped
        "head_branch": run.head_branch,
        "head_sha": run.head_sha[:7],  # Short SHA
        "event": run.event,  # push, pull_request, workflow_dispatch, etc.
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "run_started_at": run.run_started_at.isoformat() if run.run_started_at else None,
        "html_url": run.html_url,
        "actor": run.actor.login if run.actor else "unknown",
    }

def _format_comment(self, comment: Any) -> Dict[str, Any]:
    """Format GitHub comment to dict."""
    body = comment.body or ""
    max_len = 1500  # prevent overly long responses
    truncated = body[:max_len]
    if len(body) > max_len:
        truncated += "\n… (comment truncated)"
    return {
        "id": comment.id,
        "body": truncated,
        "author": comment.user.login if comment.user else "unknown",
        "created_at": comment.created_at.isoformat(),
        "updated_at": comment.updated_at.isoformat(),
        "html_url": comment.html_url,
    }
```

---

## Error Handling Standards

### Consistent Pattern Across All Tools

```python
def tool_method(self, ....) -> str:
    """Tool description."""
    try:
        # Resolve repository
        repo_full_name = self.config.get_repo_full_name(repo)
        gh_repo = self.github.get_repo(repo_full_name)

        # Perform operation
        result = gh_repo.some_operation(...)

        # Format and return success response
        return formatted_success_message

    except GithubException as e:
        # Handle specific GitHub API errors
        if e.status == 404:
            return f"Resource not found: {e.data.get('message', str(e))}"
        elif e.status == 403:
            return f"Permission denied: {e.data.get('message', str(e))}"
        elif e.status == 401:
            return "Authentication failed. Confirm the configured GitHub token has not expired."
        elif e.status == 422:
            return f"Validation error: {e.data.get('message', str(e))}"
        else:
            return f"GitHub API error: {e.data.get('message', str(e))}"

    except Exception as e:
        # Catch-all for unexpected errors
        return f"Error performing operation: {str(e)}"
```

**Key Points:**
- Never raise exceptions to LLM (always return error strings)
- Provide actionable error messages
- Include GitHub's error message when available
- Distinguish between 404 (not found), 403 (permissions), 422 (validation)
- When a 403 message mentions "rate limit", provide current usage and reset time using `self.github.rate_limiting` / `self.github.rate_limiting_resettime`; otherwise treat it as a general permission failure.

---

## Tool Registration

### Updated `create_github_tools()` Function

```python
def create_github_tools(config: AgentConfig) -> List:
    """
    Create GitHub tool functions for the agent.

    Returns list of tool functions that can be passed to agent.
    """
    tools_instance = GitHubTools(config)

    # Return comprehensive tool list grouped by domain
    return [
        # Issues (7 tools)
        tools_instance.list_issues,
        tools_instance.get_issue,
        tools_instance.get_issue_comments,
        tools_instance.create_issue,
        tools_instance.update_issue,
        tools_instance.add_issue_comment,
        tools_instance.search_issues,

        # Pull Requests (7 tools)
        tools_instance.list_pull_requests,
        tools_instance.get_pull_request,
        tools_instance.get_pr_comments,
        tools_instance.create_pull_request,
        tools_instance.update_pull_request,
        tools_instance.merge_pull_request,
        tools_instance.add_pr_comment,

        # Workflows/Actions (5 tools)
        tools_instance.list_workflows,
        tools_instance.list_workflow_runs,
        tools_instance.get_workflow_run,
        tools_instance.trigger_workflow,
        tools_instance.cancel_workflow_run,
    ]
```

**Total:** 19 LLM-accessible tools

---

## Agent Instructions Update

### Updated `agent.py` Instructions String

```python
self.instructions = f"""You are an AI assistant specialized in managing GitHub repositories for OSDU SPI services.

Organization: {self.config.organization}
Managed Repositories: {', '.join(self.config.repositories)}

Your capabilities:

ISSUES:
1. List issues with filtering (state, labels, assignees)
2. Get detailed issue information
3. Read all comments on an issue
4. Create new issues with labels and assignees
5. Update issues (title, body, labels, state, assignees)
6. Add comments to issues
7. Search issues across repositories

PULL REQUESTS:
8. List pull requests with filtering (state, base/head branches)
9. Get detailed PR information (metadata, merge readiness, conversation counts)
10. Read PR discussion comments
11. Create pull requests from branches
12. Update PR metadata (title, body, state)
13. Merge pull requests with specified merge method
14. Add comments to PR discussions

WORKFLOWS & ACTIONS:
15. List available workflows in repositories
16. List recent workflow runs with filtering
17. Get detailed workflow run information (jobs, timing, status)
18. Trigger workflows manually (if workflow_dispatch enabled)
19. Cancel running or queued workflows

GUIDELINES:
- Accept both short repository names (e.g., 'partition') and full names (e.g., 'danielscholl-osdu/partition')
- Always provide URLs for reference in your responses
- When creating issues or PRs, write clear titles and use markdown formatting
- Never merge or cancel runs unless the user explicitly requests it in the same turn; confirm the action outcome (success or failure) in the response.
- Before merging PRs, verify they are mergeable and checks have passed
- When suggesting actions, consider the full context (comments, reviews, CI status)
- Be helpful, concise, and proactive

BEST PRACTICES:
- Use get_issue_comments or get_pr_comments to understand discussion context
- Check workflow run status before triggering new runs
- Verify PR is mergeable before attempting merge
- Suggest appropriate labels based on issue/PR content
"""
```

---

## Testing Strategy

### Test Coverage Requirements

Each tool should have tests for:

1. **Happy path** - Successful operation
2. **Resource not found** (404 errors)
3. **Permission denied** (403 errors)
4. **Validation errors** (422 errors)
5. **Malformed inputs**
6. **Empty results** (e.g., no issues found)

### Mock Structure

```python
# tests/test_github_tools.py

import pytest
from unittest.mock import Mock, MagicMock
from spi_agent.github_tools import GitHubTools
from spi_agent.config import AgentConfig

@pytest.fixture
def mock_github(mocker):
    """Mock PyGithub client."""
    mock = mocker.patch("spi_agent.github_tools.Github")
    return mock.return_value

@pytest.fixture
def github_tools(mock_github):
    """Create GitHubTools instance with mocked client."""
    config = AgentConfig(
        github_token="fake_token",
        organization="test-org",
        repositories=["repo1", "repo2"]
    )
    return GitHubTools(config)

# Example test
@pytest.mark.asyncio
async def test_list_pull_requests_success(github_tools, mock_github):
    """Test listing PRs successfully."""
    # Setup mocks
    mock_repo = MagicMock()
    mock_github.get_repo.return_value = mock_repo

    mock_pr = MagicMock()
    mock_pr.number = 5
    mock_pr.title = "Test PR"
    mock_pr.state = "open"
    # ... set other attributes

    mock_repo.get_pulls.return_value = [mock_pr]

    # Execute
    result = github_tools.list_pull_requests(repo="repo1", state="open")

    # Assert
    assert "Found 1 pull request" in result
    assert "#5: Test PR" in result
    assert "[open]" in result
```

---

## Implementation Phases

### Phase 1: Core Enhancements (Immediate)
- ✅ Keep existing 6 issue tools
- 🆕 Add `get_issue_comments` (missing critical functionality)
- 📝 Update docstrings and type hints for consistency
- ✅ Keep existing formatters

**Outcome:** Complete issue management with comment reading

### Phase 2: Pull Request Support (Next)
- 🆕 Add 7 PR tools (list, get, get_comments, create, update, merge, add_comment)
- 🆕 Add `_format_pr` helper
- 🆕 Add PR-specific error handling
- ✅ Update agent instructions
- 🚫 Defer review/CI aggregation until post-launch enhancement

**Outcome:** Full PR lifecycle management

### Phase 3: Workflow Support (Final)
- 🆕 Add 5 workflow tools (list, list_runs, get_run, trigger, cancel)
- 🆕 Add `_format_workflow` and `_format_workflow_run` helpers
- 🆕 Add workflow-specific error handling
- ✅ Update agent instructions

**Outcome:** Complete GitHub operations coverage

### Phase 4: Documentation & Testing
- 📝 Update SPEC.md with new capabilities
- 🧪 Write comprehensive test suite
- 📝 Update README with examples
- 📝 Add usage examples to docs

---

## Future Enhancements (Out of Scope)

These are intentionally NOT included in initial design:

1. **Detailed PR Status Aggregation** - Review/CI summarization deferred until basic PR flows are battle-tested
2. **PR Review Management** - Too complex (review state machine, code-level comments)
3. **Issue/PR Templates** - Repository-level configuration, not runtime operations
4. **Milestone Management** - Less commonly used, can add later if needed
5. **Project Board Operations** - Different API surface, separate concern
6. **Repository Settings** - Administrative operations, security concern
7. **Branch Protection Rules** - Administrative, requires org-level permissions
8. **Workflow Logs Retrieval** - Too verbose, better to provide log URLs
9. **Detailed Job/Step Information** - Too granular, run summary is sufficient

---

## Success Metrics

### Developer Experience
- ✅ Clear tool names that map to GitHub concepts
- ✅ Comprehensive type hints (mypy clean)
- ✅ Easy to add new tools following established patterns
- ✅ Mockable for testing

### LLM Experience
- ✅ Rich parameter descriptions via Annotated/Field
- ✅ Structured output strings (not just prose)
- ✅ Consistent formatting across tools
- ✅ Actionable error messages

### User Experience
- ✅ Natural language queries map to correct tools
- ✅ Responses include URLs for reference
- ✅ Clear status indicators (✓, ✗, ⏳, 💬, 📝)
- ✅ Handles both short and full repository names

### API Efficiency
- ✅ Single GitHub client instance (connection pooling)
- ✅ Pagination parameters on list operations
- ✅ No redundant API calls
- ✅ Proper error handling (no retry storms)

---

## Migration Path

### For Existing Installations

**No Breaking Changes:**
- All existing 6 issue tools maintain same signatures
- Agent instructions are additive (new capabilities)
- Tool registration is backwards compatible

**What Changes:**
- Tool list grows from 6 → 19 tools
- Agent instructions updated with new capabilities
- New formatter methods added (doesn't affect existing tools)

### Rollout Strategy

1. **Phase 1**: Add `get_issue_comments` only
   - Test with existing usage patterns
   - Validate LLM can discover and use new tool

2. **Phase 2**: Add PR tools (metadata-first)
   - Support listing, inspecting, creating, updating, merging, and commenting without additional review/check aggregation
   - Validate merge operations are safe and error messaging is clear

3. **Phase 3**: Add workflow tools
   - Test trigger/cancel operations carefully
   - Validate permission handling

- **Optional follow-up**: Enhance PR status reporting once Phase 2 proves stable
   - Aggregate review decisions and CI statuses
   - Ensure additional API calls do not cause rate-limit issues

---

## Appendix A: Example LLM Queries

### Issues
- "List all open bugs in partition"
- "Show me issue #5 with all its comments"
- "Create an issue in legal: API returns 500 on authentication"
- "Close issue #3 in partition and add a comment saying it's fixed"
- "Search for issues mentioning 'CodeQL' across all repos"

### Pull Requests
- "List open PRs in partition"
- "Show me details for PR #5 including CI status"
- "Create a PR from feature/auth to main in partition"
- "What are people saying about PR #5?"
- "Merge PR #7 using squash merge"

### Workflows
- "What workflows are configured in partition?"
- "Show me recent workflow runs in legal"
- "Get details for workflow run #123"
- "Trigger the build workflow on the develop branch"
- "Cancel workflow run #124"

---

## Appendix B: Return Format Examples

See individual tool specifications above for detailed format examples.

**Conventions:**
- Headers use plain text with clear labels
- Lists use bullets or numbered format
- URLs always included on separate line
- Status indicators: ✓ (success), ✗ (failure), ⏳ (in progress), 💬 (comments), 📝 (files)
- Timestamps in ISO 8601 format
- Durations in human-readable format (e.g., "3m 45s")

---

## Document Version

- **Version:** 1.1
- **Date:** 2025-02-15
- **Author:** System Architecture
- **Status:** Revised Draft (post design review)

**Next Steps:**
1. Review and approve design
2. Create implementation tickets for each phase
3. Begin Phase 1 implementation
4. Write tests alongside implementation
