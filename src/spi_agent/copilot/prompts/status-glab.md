ARGUMENTS:
    SERVICES: (REQUIRED) Service name(s) to check GitLab status
    PROVIDERS: (REQUIRED) Provider labels to filter issues/MRs (e.g., Azure,Core)

INSTRUCTIONS:
    1. Parse the SERVICES argument to determine which services to check
    2. For each service, get UPSTREAM_REPO_URL from GitHub repository variables
    3. Use the GitLab CLI (`glab`) to retrieve information from upstream repositories
    4. Filter issues and merge requests by provider labels
    5. For each merge request, query its pipelines
    6. Return results ONLY as valid JSON - NO additional narrative or explanation

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
    $ gh api repos/{OWNER}/{REPO}/actions/variables/UPSTREAM_REPO_URL --jq '.value' 2>/dev/null || echo ""
    Purpose: Get the GitLab upstream repository URL from GitHub variable
    Note: If empty, skip this service

2. GET_ISSUES (filtered by provider labels):
    For each provider in PROVIDERS list, execute:
    $ glab issue list --repo {UPSTREAM_URL} --label {PROVIDER} --output json --per-page 10 2>/dev/null || echo "[]"
    Purpose: Retrieve open issues filtered by provider label
    Note: GitLab labels are case-sensitive (try "Azure" if "azure" fails)
    Note: Merge results from multiple providers, removing duplicates by iid

3. GET_MERGE_REQUESTS (filtered by provider labels):
    For each provider in PROVIDERS list, execute:
    $ glab mr list --repo {UPSTREAM_URL} --label {PROVIDER} --output json --per-page 10 2>/dev/null || echo "[]"
    Purpose: Retrieve open merge requests filtered by provider label
    Note: Same merging logic as issues

4. GET_MR_PIPELINES:
    For EACH merge request found, execute:
    $ glab ci list --repo {UPSTREAM_URL} --ref {SOURCE_BRANCH} --output json --per-page 10 2>/dev/null || echo "[]"
    Purpose: Get pipelines for this MR's source branch
    Example: If MR has source_branch="feature-xyz", run with --ref feature-xyz

    STORAGE:
    - Store the pipeline list under each MR's "pipelines" array
    - If command fails or returns nothing, the "|| echo '[]'" will provide empty array
    - This ensures the JSON structure is always valid even if pipelines can't be retrieved
    - Include up to 10 most recent pipelines per MR to capture all MR-related activity

    NOTE: We query ALL pipelines for the branch (not just merge_request_event) because:
    - Some pipelines are triggered by MR creation (source: merge_request_event)
    - Other pipelines are triggered by branch pushes (source: push)
    - Both are relevant for understanding MR health and status

5. GET_FAILED_PIPELINE_JOBS:
    For EACH pipeline with status="failed", execute:
    $ glab api projects/{PROJECT_PATH_ENCODED}/pipelines/{PIPELINE_ID}/jobs --hostname {GITLAB_HOST} --paginate 2>/dev/null || echo "[]"
    Purpose: Get detailed job information for failed pipelines to identify what failed

    IMPORTANT PATH ENCODING:
    - PROJECT_PATH must be URL-encoded (replace / with %2F)
    - Example: "osdu/platform/system/partition" becomes "osdu%2Fplatform%2Fsystem%2Fpartition"
    - Extract PROJECT_PATH from UPSTREAM_URL by removing protocol and .git suffix
    - GITLAB_HOST is the domain from UPSTREAM_URL (e.g., community.opengroup.org)

    EXAMPLE:
    If UPSTREAM_URL is "https://community.opengroup.org/osdu/platform/system/partition.git":
    - PROJECT_PATH = "osdu/platform/system/partition"
    - PROJECT_PATH_ENCODED = "osdu%2Fplatform%2Fsystem%2Fpartition"
    - GITLAB_HOST = "community.opengroup.org"
    - PIPELINE_ID = pipeline.id
    Command: glab api projects/osdu%2Fplatform%2Fsystem%2Fpartition/pipelines/333828/jobs --hostname community.opengroup.org --paginate

    STORAGE:
    - Add a "jobs" array to each failed pipeline object
    - Parse the JSON array response directly (glab api returns array of jobs)
    - If command fails or returns nothing, set "jobs": []

    JOB FIELDS TO EXTRACT (from glab api response):
    - id: Job ID
    - name: Job name
    - stage: Pipeline stage (e.g., "review", "build", "test", "deploy")
    - status: Job status (success, failed, canceled, skipped, manual)
    - duration: Job duration in seconds (may be null)
    - web_url: Job URL

    NOTE: Only fetch jobs for failed pipelines to minimize API calls

</GATHERING_TASKS>


<OUTPUT_FORMAT>

CRITICAL: After executing all the gathering commands above, your final response should be ONLY the JSON data shown below.

IMPORTANT:
- Type the JSON directly as your response text
- Do NOT use any shell commands (no cat, echo, printf, or heredocs)
- Do NOT wrap the JSON in markdown code blocks
- Do NOT add any explanatory text before or after the JSON
- Simply respond with the JSON object as plain text

{
  "timestamp": "2025-01-17T10:30:00Z",
  "projects": {
    "partition": {
      "upstream_url": "https://gitlab.com/osdu/platform/os-core-common/os-partition",
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
                "web_url": "https://gitlab.com/osdu/platform/os-partition/-/pipelines/12340",
                "jobs": [
                  {
                    "id": 98765,
                    "name": "compile-and-unit-test",
                    "stage": "build",
                    "status": "success",
                    "duration": 45,
                    "web_url": "https://gitlab.com/osdu/platform/os-partition/-/jobs/98765"
                  },
                  {
                    "id": 98766,
                    "name": "azure-containerize",
                    "stage": "containerize",
                    "status": "failed",
                    "duration": 15,
                    "web_url": "https://gitlab.com/osdu/platform/os-partition/-/jobs/98766"
                  },
                  {
                    "id": 98767,
                    "name": "ibm-deploy",
                    "stage": "deploy",
                    "status": "canceled",
                    "duration": 0,
                    "web_url": "https://gitlab.com/osdu/platform/os-partition/-/jobs/98767"
                  }
                ]
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
1. If UPSTREAM_REPO_URL doesn't exist or is empty, skip that service entirely (don't include in output)
2. If there are no issues matching provider filters, set "count": 0 and "items": []
3. If there are no MRs matching provider filters, set "count": 0 and "items": []
4. For EACH MR, query its specific pipelines and store in "pipelines" array within the MR object
5. If an MR has no pipelines, set "pipelines": [] (empty array)
6. Include up to 5 most recent pipelines per MR
7. Pipeline status values: "success", "failed", "running", "pending", "canceled", "skipped", "manual"
8. For EACH failed pipeline, include a "jobs" array with job details from `glab ci view`
9. If a pipeline is not failed, omit the "jobs" field (don't include empty array for successful pipelines)
10. Job status values: "success", "failed", "canceled", "skipped", "manual", "running", "pending"
11. When merging results from multiple provider queries, remove duplicates by iid
12. Include all labels on issues/MRs, not just the provider labels
13. For MRs, use "draft" field from glab output (not "is_draft")
14. DO NOT wrap JSON in markdown code fences or add any explanatory text
15. Extract assignees as array of usernames (from assignees[].username)
16. Extract author as string (from author.username)

PROVIDER FILTERING DETAILS:
- For each provider in the PROVIDERS list, make separate glab calls with --label {provider}
- Example: If PROVIDERS is "azure,core", run:
  - glab issue list --repo {URL} --label azure --output json (or Azure if lowercase fails)
  - glab issue list --repo {URL} --label core --output json (or Core if lowercase fails)
- Merge the results into a single list, removing duplicates by iid
- Keep all labels on each issue/MR in the output
- An issue with labels ["Azure", "Core", "bug"] should appear in results for both provider queries

FIELD MAPPING FROM GLAB JSON:
- assignees: Extract usernames from assignees[].username → ["user1", "user2"]
- author: Extract username from author.username → "username"
- labels: Use as-is (already array of strings)
- MRs: Use "draft" field directly (boolean)
- Pipelines: Use "status" field directly

</OUTPUT_FORMAT>


CRITICAL: Your response must be ONLY the JSON output. Do not include any narrative, explanations, or markdown code fences. Just raw JSON.
