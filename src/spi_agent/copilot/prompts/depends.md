ARGUMENTS:
    SERVICES: (REQUIRED) Specify service name(s) to analyze:
        - Single service: partition
        - Multiple services: partition,entitlements,legal
        - All services: all
    PROVIDERS: (OPTIONAL) Provider modules to include (default: azure):
        - Single provider: azure
        - Multiple providers: azure,aws,gcp
        - All providers: azure,aws,gcp,core
    INCLUDE_TESTING: (OPTIONAL) Include testing modules (default: false)
    CREATE_ISSUE: (OPTIONAL) Create tracking issues for updates (default: false)

INSTRUCTIONS:
    1. Parse the SERVICES argument to determine which services to analyze
    2. For each service, use the Maven MCP dependency checking capability to:
        a. Extract all dependencies from POM files
        b. Batch check versions using check_version_batch_tool
        c. Compare current versions against available versions
        d. Categorize updates as major, minor, or patch
        e. Generate prioritized update recommendations
    3. Extract key metrics from version check reports:
        - Total dependencies scanned
        - Major version updates available
        - Minor version updates available
        - Patch version updates available
        - Recommended updates with version numbers
    4. If CREATE_ISSUE is true, create GitHub tracking issues for services with available updates

SERVICE_LIST:

- partition:
    OWNER: {{ORGANIZATION}}
    REPO: partition
    TYPE: Maven multi-module project
    NOTES: Standard OSDU SPI service structure

- entitlements:
    OWNER: {{ORGANIZATION}}
    REPO: entitlements
    TYPE: Maven multi-module project
    NOTES: Entitlements v2 modules

- legal:
    OWNER: {{ORGANIZATION}}
    REPO: legal
    TYPE: Maven multi-module project
    NOTES: Standard OSDU SPI service structure

- schema:
    OWNER: {{ORGANIZATION}}
    REPO: schema
    TYPE: Maven multi-module project
    NOTES: Uses Cucumber tests

- file:
    OWNER: {{ORGANIZATION}}
    REPO: file
    TYPE: Maven multi-module project
    NOTES: Standard OSDU SPI service structure

- storage:
    OWNER: {{ORGANIZATION}}
    REPO: storage
    TYPE: Maven multi-module project
    NOTES: Standard OSDU SPI service structure

- indexer:
    OWNER: {{ORGANIZATION}}
    REPO: indexer
    TYPE: Maven multi-module project
    NOTES: Standard OSDU SPI service structure

- indexer-queue:
    OWNER: {{ORGANIZATION}}
    REPO: indexer-queue
    TYPE: Maven multi-module project
    NOTES: Unique module structure

- search:
    OWNER: {{ORGANIZATION}}
    REPO: search
    TYPE: Maven multi-module project
    NOTES: Standard OSDU SPI service structure

- workflow:
    OWNER: {{ORGANIZATION}}
    REPO: workflow
    TYPE: Maven multi-module project
    NOTES: Standard OSDU SPI service structure


<WORKING_DIRECTORY>

DIRECTORY_STRUCTURE:
    - All repository operations must occur in PROJECT_ROOT/repos/
    - Repository directory structure: PROJECT_ROOT/repos/{service_name}/
    - Example: For partition service, use repos/partition/ as the working directory
    - POM files are located at: PROJECT_ROOT/repos/{service_name}/pom.xml

</WORKING_DIRECTORY>


<MCP_DEPENDS_WORKFLOW>

DEPENDENCY_ANALYSIS_EXECUTION:
    For each service in SERVICES list:

    1. VERIFICATION PHASE:
        - Check if PROJECT_ROOT/repos/{service_name}/ directory exists
        - Check if PROJECT_ROOT/repos/{service_name}/pom.xml exists
        - If directory or POM not found:
            - Report error: "Repository not found: {service_name}. Please run /fork {service_name} first."
            - Mark service as ERROR and skip
            - Continue to next service

    2. DEPENDENCY EXTRACTION PHASE:
        - Use analyze_pom_file_tool to extract dependencies from POM
        - Collect all dependencies from parent and child modules
        - Filter dependencies based on PROVIDERS argument:
            - If PROVIDERS includes "azure": include modules in providers/azure/
            - If PROVIDERS includes "aws": include modules in providers/aws/
            - If PROVIDERS includes "gcp": include modules in providers/gcp/
            - Always include core modules
        - If INCLUDE_TESTING is false: exclude testing modules

    3. VERSION CHECKING PHASE:
        - Use check_version_batch_tool to check all dependencies
        - For each dependency, the tool returns:
            - Current version
            - Latest major version
            - Latest minor version
            - Latest patch version
            - Update availability status
        - Categorize updates:
            - Major: Current X.y.z → Latest (X+n).y.z
            - Minor: Current x.Y.z → Latest x.(Y+n).z
            - Patch: Current x.y.Z → Latest x.y.(Z+n)

    4. REPORTING PHASE:
        - Generate concise summary for the service:
            - Service name and repository URL
            - Update counts by category (major, minor, patch)
            - Top 5-10 prioritized updates with:
                - Artifact name (groupId:artifactId)
                - Current version
                - Recommended version (latest stable)
                - Update category (major/minor/patch)
                - Rationale (if available from release notes)
            - Report ID for detailed analysis

    5. ISSUE CREATION PHASE (if CREATE_ISSUE=true):
        - For services with available updates:
            - Create GitHub issue with:
                - Title: "Dependencies: [SERVICE] Update analysis - X updates available"
                - Labels: dependencies, maintenance
                - Body: Dependency summary with prioritized updates
                - Link to detailed report
            - Report issue URL

ERROR_HANDLING:
    - If MCP server unavailable:
        - Report: "✗ Maven MCP server not available. Please ensure MCP tools are enabled."
        - Skip all services
    - If repository not found:
        - Report error with guidance to run /fork first
        - Continue to next service
    - If POM parsing fails:
        - Report: "✗ Failed to parse POM file. Check Maven project structure."
        - Continue to next service
    - If version check fails for specific dependency:
        - Skip that dependency and continue with others
        - Report warning in summary
    - For any unexpected errors:
        - Report error with details
        - Continue to next service

</MCP_DEPENDS_WORKFLOW>


<OUTPUT_FORMAT>

CRITICAL: Use EXACTLY these formats so the parser can track progress and extract metrics:

STATUS_UPDATE_FORMAT:
    Use these exact patterns for status updates:
    - "✓ {service}: Starting dependency analysis"
    - "✓ {service}: Extracting dependencies from POM"
    - "✓ {service}: Checking versions"
    - "✓ {service}: Generating report"

    Examples:
    - "✓ partition: Starting dependency analysis"
    - "✓ legal: Checking versions"
    - "✓ storage: Generating report"

FINDINGS_FORMAT:
    After analysis completes, provide findings in this format:

    "✓ {service}: Analysis complete - {major} major, {minor} minor, {patch} patch updates available"

    Examples:
    - "✓ partition: Analysis complete - 3 major, 12 minor, 25 patch updates available"
    - "✓ legal: Analysis complete - 0 major, 5 minor, 18 patch updates available"
    - "✓ schema: Analysis complete - 0 major, 0 minor, 2 patch updates available"

DETAILED_FINDINGS_FORMAT:
    For each service, provide:

    **{Service Name}** ({total} dependencies scanned)
    - **Outdated**: {outdated} / {total} ({percentage}%)
    - **Major Updates**: {major_count}
      1. {artifact}:{current_version} → {latest_version}
         Category: Major | Reason: {reason}

    - **Minor Updates**: {minor_count}
      1. {artifact}:{current_version} → {latest_version}
         Category: Minor | Reason: {reason}

    - **Patch Updates**: {patch_count} (listing top 5)
      1. {artifact}:{current_version} → {latest_version}

    **Recommended Actions**:
    1. Update {artifact} to {version} (priority: {high/medium/low})
    2. Update {artifact} to {version} (priority: {high/medium/low})

    **Report**: {report_id}
    **Repository**: https://github.com/{org}/{repo}

ISSUE_CREATION_FORMAT (if CREATE_ISSUE=true):
    "✓ {service}: Created tracking issue #{issue_number}"
    "  Issue URL: {issue_url}"

IMPORTANT PARSING RULES:
    - Always use lowercase service names in status updates
    - Always include exact update counts in format: "X major, Y minor, Z patch"
    - Use the patterns above - the parser depends on these exact strings
    - Status announcements should be REGULAR TEXT, not echo/print commands
    - Include current version and recommended version for each update
    - Categorize updates correctly (major/minor/patch)

FINAL_SUMMARY:
    Aggregate summary across all services:
    - Total services analyzed
    - Total major updates available
    - Total minor updates available
    - Total patch updates available
    - Services requiring attention (major/minor available)
    - Average dependencies per service
    - Overall dependency freshness grade

</OUTPUT_FORMAT>


<EXAMPLES>

Example 1: Single service with updates available
    Input: SERVICES=partition, PROVIDERS=azure, CREATE_ISSUE=false
    Output:
        ✓ partition: Starting dependency analysis
        ✓ partition: Extracting dependencies from POM
        ✓ partition: Checking versions
        ✓ partition: Analysis complete - 2 major, 8 minor, 15 patch updates available

        **Partition Service** (87 dependencies scanned)
        - **Outdated**: 25 / 87 (29%)
        - **Major Updates**: 2
          1. org.springframework.boot:spring-boot-starter-parent:2.7.0 → 3.3.0
             Category: Major | Reason: Framework upgrade with breaking changes
          2. org.apache.logging.log4j:log4j-core:2.17.1 → 3.0.0
             Category: Major | Reason: New major version with API changes

        - **Minor Updates**: 8 (showing top 5)
          1. com.fasterxml.jackson.core:jackson-databind:2.15.0 → 2.18.0
          2. org.apache.commons:commons-lang3:3.12.0 → 3.17.0

        - **Patch Updates**: 15 (showing top 5)
          1. junit:junit:4.13.2 → 4.13.3

        **Recommended Actions**:
        1. Review Spring Boot 3.x migration guide before upgrading (priority: high)
        2. Update jackson-databind to 2.18.0 for bug fixes (priority: medium)
        3. Apply patch updates for security fixes (priority: medium)

        **Report**: partition-depends-2025-10-21
        **Repository**: https://github.com/danielscholl-osdu/partition

Example 2: Multiple services with issue creation
    Input: SERVICES=partition,legal, PROVIDERS=azure,core, CREATE_ISSUE=true
    Output:
        ✓ partition: Starting dependency analysis
        ✓ partition: Analysis complete - 2 major, 8 minor, 15 patch updates available
        ✓ partition: Created tracking issue #124
          Issue URL: https://github.com/danielscholl-osdu/partition/issues/124

        ✓ legal: Starting dependency analysis
        ✓ legal: Analysis complete - 0 major, 3 minor, 10 patch updates available
        ✓ legal: Created tracking issue #46
          Issue URL: https://github.com/danielscholl-osdu/legal/issues/46

        Summary: 2 major, 11 minor, 25 patch across 2 services

Example 3: Service with all dependencies up-to-date
    Input: SERVICES=schema, PROVIDERS=azure, CREATE_ISSUE=false
    Output:
        ✓ schema: Starting dependency analysis
        ✓ schema: Analysis complete - 0 major, 0 minor, 0 patch updates available

        **Schema Service** (52 dependencies scanned)
        - **Outdated**: 0 / 52 (0%)
        - All dependencies are up-to-date!

        **Report**: schema-depends-2025-10-21
        No action required.

</EXAMPLES>
