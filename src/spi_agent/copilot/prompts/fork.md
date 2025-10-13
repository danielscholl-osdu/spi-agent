ARGUMENTS:
    SERVICES: (REQUIRED) Specify service name(s) to process:
        - Single service: partition
        - Multiple services: partition,entitlements,legal
        - All services: all
    BRANCH: (OPTIONAL) Branch name to use (default: main)

INSTRUCTIONS: 
    1. Parse the SERVICES argument to determine which services to process
    2. If no SERVICES argument, perform the action items for each service in SERVICE_LIST
    3. If SERVICES is a comma-separated list, only process those specific services
    4. If SERVICES is a single name, only process that one service
    5. Use the BRANCH argument value, or default to 'main' if not specified
    6. Only execute the action items for the filtered service(s)
    
BRANCH_STRATEGY:
    - For BRANCH='main': Create repository directly from template (standard flow)
    - For non-main BRANCH: Clone template locally first, switch branch, then create GitHub repo
    - This ensures correct branch content is available from the start

TEMPLATE:
    REPO: azure/osdu-spi
    BRANCH: (use BRANCH argument or default to 'main') 

SERVICE_LIST:

- partition:
    OWNER: {{ORGANIZATION}}
    REPO: partition
    UPSTREAM_REPO: https://community.opengroup.org/osdu/platform/system/partition

- entitlements:
    OWNER: {{ORGANIZATION}}
    REPO: entitlements
    UPSTREAM_REPO: https://community.opengroup.org/osdu/platform/security-and-compliance/entitlements

- legal:
    OWNER: {{ORGANIZATION}}
    REPO: legal
    UPSTREAM_REPO: https://community.opengroup.org/osdu/platform/security-and-compliance/legal

- schema:
    OWNER: {{ORGANIZATION}}
    REPO: schema
    UPSTREAM_REPO: https://community.opengroup.org/osdu/platform/system/schema-service

- file:
    OWNER: {{ORGANIZATION}}
    REPO: file
    UPSTREAM_REPO: https://community.opengroup.org/osdu/platform/system/file

- storage:
    OWNER: {{ORGANIZATION}}
    REPO: storage
    UPSTREAM_REPO: https://community.opengroup.org/osdu/platform/system/storage

- indexer:
    OWNER: {{ORGANIZATION}}
    REPO: indexer
    UPSTREAM_REPO: https://community.opengroup.org/osdu/platform/system/indexer-service

- indexer-queue:
    OWNER: {{ORGANIZATION}}
    REPO: indexer-queue
    UPSTREAM_REPO: https://community.opengroup.org/osdu/platform/system/indexer-queue

- search:
    OWNER: {{ORGANIZATION}}
    REPO: search
    UPSTREAM_REPO: https://community.opengroup.org/osdu/platform/system/search-service

- workflow:
    OWNER: {{ORGANIZATION}}
    REPO: workflow
    UPSTREAM_REPO: https://community.opengroup.org/osdu/platform/data-flow/ingestion/ingestion-workflow


<BEFORE_ACTION>

BEFORE:
    IF REPO exists Terminate Workflow DO NOT CONTINUE -- SUCCESS

</BEFORE_ACTION>


<WORKING_DIRECTORY>

DIRECTORY_STRUCTURE:
    - Create 'repos' directory in PROJECT_ROOT if it doesn't exist
    - All repository clone and git operations must occur in PROJECT_ROOT/repos/
    - Repository directory structure: PROJECT_ROOT/repos/{service_name}/
    - Example: For partition service, use repos/partition/ as the target directory

</WORKING_DIRECTORY>


<ACTION_ITEMS>

CREATE_STRATEGY:
    IF BRANCH == 'main':
        - Create repo directly from template with clone (--clone) into repos/{service_name}
    ELSE:
        - Ensure repos/ directory exists in PROJECT_ROOT
        - Clone template locally to repos/{service_name} directory
        - Switch to specified BRANCH as main branch
        - Create GitHub repo from local directory (not template)
        - Push local content to GitHub

WAIT:
    Workflow Complete: Initialize Fork

READ:
    Issue: `Repository Initialization Required`

COMMENT:
    Initial issue with UPSTREAM_REPO (link only no punctuation)

WAIT:
    Workflow Complete: Initialize Complete

ON_FAILURE:
    READ:
        Open Issues:
            Follow Instructions to fix any issues:
                Example: Push Protection due to secrets
            Attempt remediation based on issue instructions
            Escalate if issues have 'human-required' label

FINALIZE:
    IF branch was switched locally:
        - Pull latest changes to existing local clone in repos/{service_name}
    ELSE:
        - Ensure repos/ directory exists in PROJECT_ROOT
        - Clone forked repo from GitHub into repos/{service_name}

</ACTION_ITEMS>

<AFTER_ACTION>

REPORT:
    Output exactly: "✅ Successfully completed workflow for <service_name> service"
    Then provide summary of things accomplished

</AFTER_ACTION>
