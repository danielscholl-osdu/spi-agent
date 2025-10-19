Execute a GitLab status check for OSDU SPI services and return structured JSON output.

You will receive SERVICES and PROVIDERS arguments at the end of this prompt. Your task is to:

1. Parse the SERVICES argument to determine which services to check
2. For each service, get UPSTREAM_REPO_URL from GitHub repository variables
3. Use the GitLab CLI (`glab`) to retrieve information from upstream repositories
4. Filter issues and merge requests by provider labels
5. For EACH merge request found, query its specific pipelines (see step 5 in GATHERING_TASKS below)
6. Return results ONLY as valid JSON - NO additional narrative, explanations, or markdown
7. After outputting the JSON, EXIT IMMEDIATELY - do not wait for confirmation

CRITICAL: This is an automated workflow. DO NOT ask questions or wait for user input.

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

For each service, execute the following commands:

1. GET_UPSTREAM_URL:
    $ gh api repos/{OWNER}/{REPO}/actions/variables/UPSTREAM_REPO_URL --jq '.value'
    Purpose: Get the GitLab upstream repository URL from GitHub variable
    Example output: https://gitlab.com/osdu/platform/os-core-common/os-partition

2. CHECK_PROJECT_EXISTS:
    $ glab repo view {UPSTREAM_URL} --output json
    Purpose: Verify GitLab project exists and get basic info
    Note: Use the URL from step 1

3. GET_ISSUES (filtered by provider labels):
    For each provider in PROVIDERS list, execute:
    $ glab issue list --repo {UPSTREAM_URL} --label {PROVIDER} --output json --per-page 10
    Purpose: Retrieve open issues filtered by provider label (azure, core, etc.)
    Note: If PROVIDERS is "azure,core", run this once with --label azure and once with --label core, then merge results
    Note: Remove duplicates if an issue has multiple matching labels
    Note: GitLab labels may be capitalized (e.g., "Azure" not "azure") - try both if needed
    Note: Extract assignees from glab JSON: assignees array contains objects with "username" field
    Note: Extract author from glab JSON: author object has "username" field

4. GET_MERGE_REQUESTS (filtered by provider labels):
    For each provider in PROVIDERS list, execute:
    $ glab mr list --repo {UPSTREAM_URL} --label {PROVIDER} --output json --per-page 10
    Purpose: Retrieve open merge requests filtered by provider label
    Note: Same merging logic as issues - combine results from multiple provider queries

5. GET_MR_PIPELINES:
    For EACH merge request retrieved in step 4, execute this command:

    $ glab ci list --repo {UPSTREAM_URL} --ref {SOURCE_BRANCH} --output json --per-page 10 2>/dev/null || echo "[]"

    Purpose: Get ALL pipelines for this MR's source branch (includes both MR events and regular pushes)
    Example: For MR 710 with source_branch="port-user-auth-feature":
             glab ci list --repo "$GITLAB_URL" --ref port-user-auth-feature --output json --per-page 10 2>/dev/null || echo "[]"

    STORAGE:
    - Store the pipeline list under each MR's "pipelines" array
    - If command fails or returns nothing, the "|| echo '[]'" will provide empty array
    - This ensures the JSON structure is always valid even if pipelines can't be retrieved
    - Include up to 10 most recent pipelines per MR to capture all MR-related activity

    NOTE: We query ALL pipelines for the branch (not just merge_request_event) because:
    - Some pipelines are triggered by MR creation (source: merge_request_event)
    - Other pipelines are triggered by branch pushes (source: push)
    - Both are relevant for understanding MR health and status

</GATHERING_TASKS>


<OUTPUT_FORMAT>

CRITICAL: Your response must be ONLY the JSON output below. Do not include any narrative, explanations, or markdown code fences. Just raw JSON.

CRITICAL EXIT BEHAVIOR:
- After outputting the JSON, your task is COMPLETE
- EXIT IMMEDIATELY - do not wait for confirmation
- DO NOT ask follow-up questions
- DO NOT wait for user input
- Simply output the JSON and the process will terminate automatically

{
  "timestamp": "2025-01-17T10:30:00Z",
  "projects": {
    "partition": {
      "upstream_url": "https://gitlab.com/osdu/platform/os-core-common/os-partition",
      "project": {
        "name": "partition",
        "path_with_namespace": "osdu/platform/os-core-common/os-partition",
        "web_url": "https://gitlab.com/osdu/platform/os-core-common/os-partition",
        "last_activity_at": "2025-01-17T09:15:00Z",
        "exists": true
      },
      "issues": {
        "count": 2,
        "items": [
          {
            "iid": 42,
            "title": "Fix Azure authentication",
            "labels": ["azure", "bug"],
            "state": "opened",
            "assignees": ["john.doe"],
            "author": "jane.smith",
            "created_at": "2025-01-15T10:00:00Z",
            "web_url": "https://gitlab.com/osdu/platform/os-partition/-/issues/42"
          },
          {
            "iid": 38,
            "title": "Update Core API",
            "labels": ["core", "enhancement"],
            "state": "opened",
            "assignees": [],
            "author": "bob.jones",
            "created_at": "2025-01-14T14:30:00Z",
            "web_url": "https://gitlab.com/osdu/platform/os-partition/-/issues/38"
          }
        ]
      },
      "merge_requests": {
        "count": 1,
        "items": [
          {
            "iid": 15,
            "title": "feat: add Azure support",
            "labels": ["azure", "enhancement"],
            "state": "opened",
            "source_branch": "feature/azure",
            "target_branch": "main",
            "draft": false,
            "author": "jane.smith",
            "detailed_merge_status": "mergeable",
            "has_conflicts": false,
            "created_at": "2025-01-16T08:00:00Z",
            "web_url": "https://gitlab.com/osdu/platform/os-partition/-/merge_requests/15",
            "pipelines": [
              {
                "id": 12340,
                "status": "failed",
                "ref": "refs/merge-requests/15/head",
                "sha": "xyz789abc123",
                "created_at": "2025-01-17T07:00:00Z",
                "duration": 85,
                "web_url": "https://gitlab.com/osdu/platform/os-partition/-/pipelines/12340"
              },
              {
                "id": 12335,
                "status": "success",
                "ref": "refs/merge-requests/15/head",
                "sha": "abc789def123",
                "created_at": "2025-01-16T18:00:00Z",
                "duration": 95,
                "web_url": "https://gitlab.com/osdu/platform/os-partition/-/pipelines/12335"
              }
            ]
          }
        ]
      }
    }
  }
}

IMPORTANT RULES:
1. If UPSTREAM_REPO_URL variable doesn't exist, set "exists": false and "upstream_url": null
2. If a GitLab project doesn't exist at the URL, set "exists": false in the project object
3. If there are no issues matching provider filters, set "count": 0 and "items": []
4. If there are no MRs matching provider filters, set "count": 0 and "items": []
5. For EACH MR, query its specific pipelines (step 5) and store in "pipelines" array within the MR object
6. If an MR has no pipelines, set "pipelines": [] (empty array)
7. Include up to 5 most recent pipelines per MR
8. Pipeline status can be: "success", "failed", "running", "pending", "canceled", "skipped", "manual"
9. When merging results from multiple provider queries, remove duplicates (same iid)
10. Include all labels on issues/MRs, not just the provider labels
11. For MRs, use "draft" field from glab output (not "is_draft")
12. DO NOT wrap JSON in markdown code fences or add any explanatory text
13. Use exact field names from glab JSON output (e.g., "path_with_namespace", "last_activity_at", "detailed_merge_status")

PROVIDER FILTERING DETAILS:
- For each provider in the PROVIDERS list, make separate glab calls with --label {provider}
- Example: If PROVIDERS is "azure,core", run:
  - glab issue list --repo {URL} --label azure --output json (or Azure if lowercase fails)
  - glab issue list --repo {URL} --label core --output json (or Core if lowercase fails)
- Merge the results into a single list, removing duplicates by iid
- Keep all labels on each issue/MR in the output
- An issue with labels ["Azure", "Core", "bug"] should appear in results for both provider queries

FIELD MAPPING FROM GLAB JSON:
- Issues/MRs: assignees array has objects with "username" field → extract ["username1", "username2"]
- Issues/MRs: author object has "username" field → extract just the username string
- Issues/MRs: labels array is already strings → use as-is
- MRs: "draft" field (boolean) → map to "draft" in output
- Project: "path_with_namespace" → use for path field
- Project: "last_activity_at" → use for last update
- Pipelines: "status" field (no conclusion like GitHub workflows)

</OUTPUT_FORMAT>


FINAL REMINDER:
=================
Your ONLY output should be the JSON object above. Do not include:
- Markdown code fences (```json)
- Explanatory text before or after the JSON
- Follow-up questions or suggestions
- Confirmation requests

After outputting the JSON, your task is DONE. Exit immediately.
