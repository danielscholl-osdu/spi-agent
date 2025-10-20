ARGUMENTS:
    SERVICES: (REQUIRED) Specify service name(s) to analyze:
        - Single service: partition
        - Multiple services: partition,entitlements,legal
        - All services: all
    SEVERITY_FILTER: (OPTIONAL) Severity levels to include (default: critical,high,medium):
        - Critical only: critical
        - Critical + High: critical,high
        - All levels: critical,high,medium,low
    CREATE_ISSUE: (OPTIONAL) Create tracking issues for findings (default: false)

INSTRUCTIONS:
    1. Parse the SERVICES argument to determine which services to analyze
    2. For each service, use the Maven MCP vulnerability scanning capability to:
        a. Analyze project dependencies and version status
        b. Scan for security vulnerabilities using Trivy (if available)
        c. Correlate vulnerabilities with dependency versions
        d. Generate prioritized findings report
    3. Extract key metrics from vulnerability scan reports:
        - Total dependencies scanned
        - Critical vulnerabilities (CVE IDs and CVSS scores)
        - High severity vulnerabilities
        - Medium severity vulnerabilities
        - Recommended updates with version numbers
    4. If CREATE_ISSUE is true, create GitHub tracking issues for critical/high findings

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


<MCP_TRIAGE_WORKFLOW>

TRIAGE_EXECUTION:
    For each service in SERVICES list:

    1. VERIFICATION PHASE:
        - Check if PROJECT_ROOT/repos/{service_name}/ directory exists
        - Check if PROJECT_ROOT/repos/{service_name}/pom.xml exists
        - If directory or POM not found:
            - Report error: "Repository not found: {service_name}. Please run /fork {service_name} first."
            - Mark service as ERROR and skip
            - Continue to next service

    2. TRIAGE ANALYSIS PHASE:
        - Use MCP triage prompt for the service
        - The MCP server will:
            a. Discover project structure and POM hierarchy
            b. Extract all dependencies and managed versions
            c. Check for available updates (major/minor/patch)
            d. Scan for security vulnerabilities (if Trivy available)
            e. Correlate CVEs with affected dependencies
            f. Generate prioritized remediation plan
        - Capture triage report ID for reference

    3. FINDINGS EXTRACTION PHASE:
        - Parse triage report to extract:
            - Total dependencies scanned
            - Critical vulnerabilities: count, CVE IDs, CVSS scores, affected artifacts
            - High vulnerabilities: count, CVE IDs, affected artifacts
            - Medium vulnerabilities: count (summary only unless requested)
            - Recommended updates: artifact, current version → target version
        - Filter findings based on SEVERITY_FILTER argument

    4. REPORTING PHASE:
        - Generate concise summary for the service:
            - Service name and repository URL
            - Vulnerability counts by severity
            - Top 3-5 prioritized fixes with:
                - Artifact name (groupId:artifactId)
                - Current version
                - Recommended version
                - CVE IDs (if security-related)
                - Risk level and rationale
            - Report ID for detailed analysis

    5. ISSUE CREATION PHASE (if CREATE_ISSUE=true):
        - For services with Critical or High vulnerabilities:
            - Create GitHub issue with:
                - Title: "Security: [SERVICE] Dependency triage - X critical, Y high vulnerabilities"
                - Labels: security, dependencies
                - Body: Triage summary with prioritized fixes
                - Link to detailed report
            - Report issue URL

ERROR_HANDLING:
    - If MCP server unavailable:
        - Report: "✗ Maven MCP server not available. Please ensure MCP tools are enabled."
        - Skip all services
    - If Trivy not installed (vulnerability scanning fails):
        - Report: "⚠ Trivy not found. Continuing with version analysis only."
        - Complete triage without vulnerability data
    - If repository not found:
        - Report error with guidance to run /fork first
        - Continue to next service
    - If POM parsing fails:
        - Report: "✗ Failed to parse POM file. Check Maven project structure."
        - Continue to next service
    - For any unexpected errors:
        - Report error with details
        - Continue to next service

</MCP_TRIAGE_WORKFLOW>


<OUTPUT_FORMAT>

CRITICAL: Use EXACTLY these formats so the parser can track progress and extract metrics:

STATUS_UPDATE_FORMAT:
    Use these exact patterns for status updates:
    - "✓ {service}: Starting triage analysis"
    - "✓ {service}: Scanning for vulnerabilities"
    - "✓ {service}: Analyzing dependencies"
    - "✓ {service}: Generating report"

    Examples:
    - "✓ partition: Starting triage analysis"
    - "✓ legal: Scanning for vulnerabilities"
    - "✓ storage: Generating report"

FINDINGS_FORMAT:
    After analysis completes, provide findings in this format:

    "✓ {service}: Analysis complete - {critical} critical, {high} high, {medium} medium vulnerabilities"

    Examples:
    - "✓ partition: Analysis complete - 3 critical, 5 high, 12 medium vulnerabilities"
    - "✓ legal: Analysis complete - 0 critical, 2 high, 8 medium vulnerabilities"
    - "✓ schema: Analysis complete - 0 critical, 0 high, 1 medium vulnerabilities"

DETAILED_FINDINGS_FORMAT:
    For each service, provide:

    **{Service Name}** ({dependencies} dependencies scanned)
    - **Critical**: {count} vulnerabilities
      1. {artifact}:{current_version} → {recommended_version}
         CVE: {cve_ids} | CVSS: {score} | Risk: {description}

    - **High**: {count} vulnerabilities
      1. {artifact}:{current_version} → {recommended_version}
         CVE: {cve_ids} | Risk: {description}

    - **Medium**: {count} vulnerabilities (summary only)

    **Recommended Actions**:
    1. Update {artifact} to {version} (addresses {cve_count} CVEs)
    2. Update {artifact} to {version} (security patch)

    **Report**: {report_id}
    **Repository**: https://github.com/{org}/{repo}

ISSUE_CREATION_FORMAT (if CREATE_ISSUE=true):
    "✓ {service}: Created tracking issue #{issue_number}"
    "  Issue URL: {issue_url}"

IMPORTANT PARSING RULES:
    - Always use lowercase service names in status updates
    - Always include exact vulnerability counts in format: "X critical, Y high, Z medium"
    - Use the patterns above - the parser depends on these exact strings
    - Status announcements should be REGULAR TEXT, not echo/print commands
    - Include CVE IDs when available
    - Include CVSS scores for critical vulnerabilities
    - Provide artifact name, current version, and recommended version

FINAL_SUMMARY:
    Aggregate summary across all services:
    - Total services analyzed
    - Total critical vulnerabilities
    - Total high vulnerabilities
    - Total medium vulnerabilities
    - Services requiring immediate action (critical/high findings)
    - Average dependencies per service

</OUTPUT_FORMAT>


<EXAMPLES>

Example 1: Single service with critical findings
    Input: SERVICES=partition, SEVERITY_FILTER=critical,high, CREATE_ISSUE=false
    Output:
        ✓ partition: Starting triage analysis
        ✓ partition: Analyzing dependencies
        ✓ partition: Scanning for vulnerabilities
        ✓ partition: Analysis complete - 3 critical, 5 high, 0 medium vulnerabilities

        **Partition Service** (87 dependencies scanned)
        - **Critical**: 3 vulnerabilities
          1. org.apache.logging.log4j:log4j-core:2.14.1 → 2.25.2
             CVE: CVE-2021-44228, CVE-2021-45046 | CVSS: 10.0 | Risk: Remote code execution
          2. com.fasterxml.jackson.core:jackson-databind:2.13.0 → 2.20.0
             CVE: CVE-2022-42003 | CVSS: 7.5 | Risk: Deserialization vulnerability

        **Recommended Actions**:
        1. Update log4j-core to 2.25.2 (CRITICAL - addresses RCE)
        2. Update jackson-databind to 2.20.0 (addresses 3 CVEs)

        **Report**: partition-triage-2025-10-14
        **Repository**: https://github.com/danielscholl-osdu/partition

Example 2: Multiple services with issue creation
    Input: SERVICES=partition,legal, SEVERITY_FILTER=critical,high, CREATE_ISSUE=true
    Output:
        ✓ partition: Starting triage analysis
        ✓ partition: Analysis complete - 3 critical, 5 high, 12 medium vulnerabilities
        ✓ partition: Created tracking issue #123
          Issue URL: https://github.com/danielscholl-osdu/partition/issues/123

        ✓ legal: Starting triage analysis
        ✓ legal: Analysis complete - 0 critical, 2 high, 8 medium vulnerabilities
        ✓ legal: Created tracking issue #45
          Issue URL: https://github.com/danielscholl-osdu/legal/issues/45

        Summary: 3 critical, 7 high, 20 medium across 2 services

Example 3: Service with no critical findings
    Input: SERVICES=schema, SEVERITY_FILTER=critical,high,medium, CREATE_ISSUE=false
    Output:
        ✓ schema: Starting triage analysis
        ✓ schema: Analysis complete - 0 critical, 0 high, 1 medium vulnerabilities

        **Schema Service** (52 dependencies scanned)
        - **Critical**: 0 vulnerabilities
        - **High**: 0 vulnerabilities
        - **Medium**: 1 vulnerability
          1. commons-io:commons-io:2.11.0 → 2.17.0
             Minor security improvement

        **Report**: schema-triage-2025-10-14
        No immediate action required.

</EXAMPLES>
