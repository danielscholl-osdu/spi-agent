ARGUMENTS:
    SERVICES: (REQUIRED) Specify service name(s) to process:
        - Single service: partition
        - Multiple services: partition,entitlements,legal
        - All services: all
    PROVIDER: (OPTIONAL) Cloud provider profile(s) to test (default: azure):
        - Single provider: azure, aws, gc, ibm, core
        - Multiple providers: azure,aws
        - All providers: all

INSTRUCTIONS:
    1. Parse the SERVICES argument to determine which services to test
    2. If no SERVICES argument, process all services in SERVICE_LIST
    3. If SERVICES is a comma-separated list, only process those specific services
    4. If SERVICES is a single name, only process that one service
    5. Parse the PROVIDER argument (default: azure if not specified)
    6. For each service, execute Maven build phases: compile, test, and coverage

PROVIDER_MAPPING:
    - azure → -Pazure (default when not specified)
    - aws → -Paws
    - gc → -Pgc
    - ibm → -Pibm
    - core → -Pcore
    - all → -Pazure,aws,gc,ibm
    - Multiple (e.g., "azure,aws") → -Pazure,aws

    Note: The 'core' profile is activeByDefault=true in most services, so it's always included.

SERVICE_LIST:

- partition:
    OWNER: {{ORGANIZATION}}
    REPO: partition
    MAVEN_PROFILES: azure, aws, gc, ibm, core
    NOTES: Standard multi-module Maven structure

- entitlements:
    OWNER: {{ORGANIZATION}}
    REPO: entitlements
    MAVEN_PROFILES: azure, aws, gc, ibm, core
    NOTES: Directory is 'entitlements' but modules are 'entitlements-v2-*'

- legal:
    OWNER: {{ORGANIZATION}}
    REPO: legal
    MAVEN_PROFILES: azure, aws, gc, ibm, core
    NOTES: Standard multi-module Maven structure

- schema:
    OWNER: {{ORGANIZATION}}
    REPO: schema
    MAVEN_PROFILES: azure, aws, gc, ibm, core
    NOTES: Uses Cucumber tests with Failsafe plugin for integration tests

- file:
    OWNER: {{ORGANIZATION}}
    REPO: file
    MAVEN_PROFILES: azure, aws, gc, ibm, core
    NOTES: Standard multi-module Maven structure

- storage:
    OWNER: {{ORGANIZATION}}
    REPO: storage
    MAVEN_PROFILES: azure, aws, gc, ibm, core
    NOTES: Standard multi-module Maven structure

- indexer:
    OWNER: {{ORGANIZATION}}
    REPO: indexer
    MAVEN_PROFILES: azure, aws, gc, ibm, core
    NOTES: Standard multi-module Maven structure

- indexer-queue:
    OWNER: {{ORGANIZATION}}
    REPO: indexer-queue
    MAVEN_PROFILES: azure, aws, gc, ibm, core
    NOTES: Unique module structure, tests in root module

- search:
    OWNER: {{ORGANIZATION}}
    REPO: search
    MAVEN_PROFILES: azure, aws, gc, ibm, core
    NOTES: Standard multi-module Maven structure

- workflow:
    OWNER: {{ORGANIZATION}}
    REPO: workflow
    MAVEN_PROFILES: azure, aws, gc, ibm, core
    NOTES: Standard multi-module Maven structure


<WORKING_DIRECTORY>

DIRECTORY_STRUCTURE:
    - All repository operations must occur in PROJECT_ROOT/repos/
    - Repository directory structure: PROJECT_ROOT/repos/{service_name}/
    - Example: For partition service, use repos/partition/ as the working directory
    - Maven commands must be executed from within each service's repository directory

</WORKING_DIRECTORY>


<BUILD_SYSTEM_DETECTION>

MAVEN_DETECTION:
    - Check for pom.xml file in PROJECT_ROOT/repos/{service_name}/
    - If pom.xml exists, this is a Maven project
    - Maven version 3.6+ required
    - Java 17+ required for OSDU SPI services

</BUILD_SYSTEM_DETECTION>


<ACTION_ITEMS>

ENSURE_REPO_EXISTS:
    - For each service in SERVICES list:
        - Check if PROJECT_ROOT/repos/{service_name}/ directory exists
        - If directory does not exist:
            - Report error: "Repository not found: {service_name}. Please run /fork {service_name} first."
            - Mark service as ERROR and skip remaining phases
            - Continue to next service
        - If directory exists:
            - Continue to COMPILE_PHASE

COMPILE_PHASE:
    - Change directory to PROJECT_ROOT/repos/{service_name}/
    - Construct Maven compile command with provider profiles:
        - Base command: mvn clean compile
        - Add profiles from PROVIDER argument: -P{profiles}
        - Example: mvn clean compile -Pazure
        - Example (multiple): mvn clean compile -Pazure,aws
    - Execute Maven compile command
    - Monitor output for:
        - Compilation start: "[INFO] Compiling" or "maven-compiler-plugin"
        - Compilation errors: "[ERROR]" or "compilation failed"
        - Build success: "[INFO] BUILD SUCCESS"
        - Build failure: "[INFO] BUILD FAILURE"
    - Report compilation result:
        - Success: "✓ Compilation successful"
        - Failure: "✗ Compilation failed" with error details
    - If compilation fails:
        - Skip TEST_PHASE and COVERAGE_PHASE for this service
        - Continue to next service

TEST_PHASE:
    - Only execute if COMPILE_PHASE succeeded
    - Construct Maven test command:
        - Base command: mvn test
        - Add profiles: -P{profiles}
        - Skip integration tests: -DskipITs
        - Full example: mvn test -Pazure -DskipITs
    - Execute Maven test command
    - Monitor output for:
        - Test execution: "maven-surefire-plugin" or "Running tests"
        - Test results: "Tests run: X, Failures: Y, Errors: Z"
        - Test summary: "Results:"
        - Build success/failure
    - Parse test results:
        - Extract total tests run
        - Extract test failures count
        - Extract test errors count
    - Report test result:
        - All passed: "✓ All X tests passed"
        - Some failed: "✗ Y of X tests failed" with failure details
    - If tests fail:
        - Continue to COVERAGE_PHASE (coverage can still be generated)

COVERAGE_PHASE:
    - Only execute if TEST_PHASE completed (regardless of pass/fail)
    - Check if JaCoCo is configured (look for jacoco-maven-plugin in pom.xml)
    - If JaCoCo is available:
        - Execute: mvn jacoco:report
        - Monitor output for coverage generation
        - Parse coverage report if available:
            - Look for coverage percentages in output
            - Extract line coverage: "Line coverage: X%"
            - Extract branch coverage: "Branch coverage: Y%"
        - Report coverage:
            - "📊 Coverage: Line X%, Branch Y%"
            - If coverage data not available: "Coverage report generated in target/site/jacoco/"
    - If JaCoCo not configured:
        - Skip this phase
        - Report: "Coverage plugin not configured"

ERROR_HANDLING:
    - If Maven command not found:
        - Report: "✗ Maven not found. Please install Maven (https://maven.apache.org/install.html)"
        - Skip all remaining services
    - If Java version incompatible:
        - Report: "✗ Java 17+ required. Current version: {version}"
        - Skip all remaining services
    - If repository not found:
        - Report error with guidance to run /fork first
        - Continue to next service
    - If compilation fails:
        - Report compilation error details
        - Skip test and coverage phases for this service
        - Continue to next service
    - For any unexpected errors:
        - Report error with details
        - Continue to next service

</ACTION_ITEMS>


<OUTPUT_FORMAT>

CRITICAL: Use EXACTLY these status update formats so the parser can track progress:

PHASE_START_FORMAT:
    Before starting each phase, announce it using EXACTLY this format:
    - "✓ {service}: Starting compile phase"
    - "✓ {service}: Starting test phase"
    - "✓ {service}: Starting coverage phase"

    Examples:
    - "✓ partition: Starting compile phase"
    - "✓ legal: Starting test phase"
    - "✓ schema: Starting coverage phase"

PHASE_COMPLETION_FORMAT:
    After each service completes ALL phases, provide a summary using EXACTLY this format:

    When tests exist and ran successfully:
    - "✓ {service}: Compiled successfully, {N} tests passed, Coverage report generated"
    - "✓ {service}: Compiled successfully, {N} tests passed" (if coverage failed/unavailable)

    When no tests are found (test count is 0 or no test classes exist):
    - "✓ {service}: Compiled successfully, 0 tests passed" (use 0, not "no tests found")

    When compilation fails:
    - "✗ {service}: Compilation failed" (skip this service and move to next)

    Examples:
    - "✓ partition: Compiled successfully, 61 tests passed, Coverage report generated"
    - "✓ entitlements: Compiled successfully, 7 tests passed, Coverage report generated"
    - "✓ indexer-queue: Compiled successfully, 0 tests passed" (service with no tests)
    - "✗ file: Compilation failed" (build error)

IMPORTANT PARSING RULES:
    - Always use lowercase service names in status updates (partition, not Partition)
    - Always include the test count in the completion summary
    - Use the exact format above - the parser depends on these patterns
    - Do NOT use markdown bold (**service**) in status updates
    - Output status announcements as REGULAR TEXT in your response - DO NOT use echo or print commands
    - Status announcements should come AFTER you verify the phase completed, not before
    - Example: Run the compile command, verify it succeeded, THEN output "✓ partition: Starting test phase"

FINAL_REPORT:
    For each service, provide:
    - Service name
    - Provider profiles used
    - Compilation status (success/failed)
    - Test results (if tests ran): Tests run, Failures, Errors
    - Coverage percentages (if available): Line %, Branch %
    - Overall status (success/failed)

    Aggregate summary:
    - Total services tested
    - Services compiled successfully
    - Services with passing tests
    - Services with test failures
    - Average code coverage (if available)

</OUTPUT_FORMAT>


<EXAMPLES>

Example 1: Single service with default provider (azure)
    Input: SERVICES=partition, PROVIDER=azure
    Actions:
        1. Check repos/partition/ exists
        2. Execute: mvn clean compile -Pazure
        3. Execute: mvn test -Pazure -DskipITs
        4. Execute: mvn jacoco:report
    Output:
        ✓ partition: Compiled successfully
        ✓ partition: All 42 tests passed
        📊 partition: Coverage - Line 78%, Branch 65%

Example 2: Multiple services with multiple providers
    Input: SERVICES=partition,legal, PROVIDER=azure,aws
    Actions:
        1. For partition:
            - mvn clean compile -Pazure,aws
            - mvn test -Pazure,aws -DskipITs
            - mvn jacoco:report
        2. For legal:
            - mvn clean compile -Pazure,aws
            - mvn test -Pazure,aws -DskipITs
            - mvn jacoco:report
    Output:
        ✓ partition: Compiled, 42 tests passed, Coverage 78%/65%
        ✓ legal: Compiled, 38 tests passed, Coverage 82%/70%

Example 3: Service with compilation error
    Input: SERVICES=partition, PROVIDER=azure
    Actions:
        1. mvn clean compile -Pazure
        2. Compilation fails
        3. Skip test and coverage phases
    Output:
        ✗ partition: Compilation failed
        Error: [ERROR] /path/to/File.java:[10,8] cannot find symbol

Example 4: Repository not found
    Input: SERVICES=partition, PROVIDER=azure
    Actions:
        1. Check repos/partition/ - NOT FOUND
        2. Skip all phases
    Output:
        ✗ partition: Repository not found
        Guidance: Run /fork partition first to clone the repository

</EXAMPLES>
