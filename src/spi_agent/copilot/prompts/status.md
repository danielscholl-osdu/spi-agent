ARGUMENTS:
    SERVICES: (REQUIRED) Specify service name(s) to check status:
        - Single service: partition
        - Multiple services: partition,entitlements,legal
        - All services: all

INSTRUCTIONS:
    1. Parse the SERVICES argument to determine which services to check
    2. For each service, gather GitHub repository status information
    3. Use the GitHub CLI (`gh`) to retrieve information
    4. Process all services in parallel where possible
    5. Return results ONLY as valid JSON - NO additional narrative or explanation

SERVICE_LIST:
- partition:
    OWNER: {{ORGANIZATION}}
    REPO: partition

- entitlements:
    OWNER: {{ORGANIZATION}}
    REPO: entitlements

- legal:
    OWNER: {{ORGANIZATION}}
    REPO: legal

- schema:
    OWNER: {{ORGANIZATION}}
    REPO: schema

- file:
    OWNER: {{ORGANIZATION}}
    REPO: file

- storage:
    OWNER: {{ORGANIZATION}}
    REPO: storage

- indexer:
    OWNER: {{ORGANIZATION}}
    REPO: indexer

- indexer-queue:
    OWNER: {{ORGANIZATION}}
    REPO: indexer-queue

- search:
    OWNER: {{ORGANIZATION}}
    REPO: search

- workflow:
    OWNER: {{ORGANIZATION}}
    REPO: workflow


<GATHERING_TASKS>

For each service, execute the following GitHub CLI commands:

1. CHECK_REPO_EXISTS:
    $ gh repo view {OWNER}/{REPO} --json name,url,updatedAt
    Purpose: Verify repository exists and get basic info

2. GET_ISSUES:
    $ gh issue list --repo {OWNER}/{REPO} --json number,title,labels,state --limit 10
    Purpose: Retrieve open issues

3. GET_PULL_REQUESTS:
    $ gh pr list --repo {OWNER}/{REPO} --json number,title,state,headRefName,isDraft --limit 10
    Purpose: Retrieve open pull requests (highlight release PRs with "chore: release" or "release" in title)

4. GET_WORKFLOW_RUNS:
    $ gh run list --repo {OWNER}/{REPO} --json name,status,conclusion,createdAt,updatedAt --limit 10
    Purpose: Get recent workflow runs (includes CodeQL, Build, Test, etc.)

</GATHERING_TASKS>


<OUTPUT_FORMAT>

CRITICAL: Your response must be ONLY the JSON output below. Do not include any narrative, explanations, or markdown code fences. Just raw JSON.

{
  "timestamp": "2025-01-06T10:30:00Z",
  "services": {
    "partition": {
      "repo": {
        "name": "partition",
        "full_name": "danielscholl-osdu/partition",
        "url": "https://github.com/danielscholl-osdu/partition",
        "updated_at": "2025-01-06T09:15:00Z",
        "exists": true
      },
      "issues": {
        "count": 2,
        "items": [
          {
            "number": 1,
            "title": "Repository Initialization Required",
            "labels": ["initialization"],
            "state": "open"
          },
          {
            "number": 2,
            "title": "Update documentation",
            "labels": ["documentation"],
            "state": "open"
          }
        ]
      },
      "pull_requests": {
        "count": 1,
        "items": [
          {
            "number": 12,
            "title": "chore: release 1.0.0",
            "state": "open",
            "branch": "main",
            "is_draft": false,
            "is_release": true
          }
        ]
      },
      "workflows": {
        "recent": [
          {
            "name": "Build",
            "status": "completed",
            "conclusion": "success",
            "created_at": "2025-01-06T09:00:00Z",
            "updated_at": "2025-01-06T09:05:00Z"
          },
          {
            "name": "CodeQL Analysis",
            "status": "completed",
            "conclusion": "success",
            "created_at": "2025-01-06T08:45:00Z",
            "updated_at": "2025-01-06T09:12:00Z"
          },
          {
            "name": "Test",
            "status": "in_progress",
            "conclusion": null,
            "created_at": "2025-01-06T09:00:00Z",
            "updated_at": "2025-01-06T09:03:00Z"
          }
        ]
      }
    }
  }
}

IMPORTANT RULES:
1. If a repository doesn't exist, set "exists": false in the repo object
2. If there are no issues, set "count": 0 and "items": []
3. If there are no PRs, set "count": 0 and "items": []
4. For workflows, include up to 10 most recent runs (all types: Build, Test, CodeQL, etc.)
5. Detect release PRs by checking if title contains "release" or "chore: release"
6. Workflow status can be: "completed", "in_progress", "queued", "waiting", etc.
7. If conclusion is null, the workflow is still running
8. DO NOT wrap JSON in markdown code fences or add any explanatory text

</OUTPUT_FORMAT>
