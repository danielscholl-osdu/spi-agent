ARGUMENTS:
    SERVICES: (REQUIRED) Specify service name(s) to process:
        - Single service: partition
        - Multiple services: partition,entitlements,legal
        - All services: all
    PROVIDER: (OPTIONAL) Cloud provider profile(s) to test (default: core,core-plus,azure):
        - Single provider: azure, aws, gc, ibm, core
        - Multiple providers: azure,aws
        - All providers: all

INSTRUCTIONS:
    1. Parse the SERVICES argument to determine which services to test
    2. If no SERVICES argument, process all services in SERVICE_LIST
    3. If SERVICES is a comma-separated list, only process those specific services
    4. If SERVICES is a single name, only process that one service
    5. Parse the PROVIDER argument (default: core,core-plus,azure if not specified)
    6. For each service, execute Maven build phases: compile, test, and coverage

PROVIDER_MAPPING:
    - core,core-plus,azure → -Pcore,core-plus,azure (default when not specified)
    - azure → -Pazure
    - aws → -Paws
    - gc → -Pgc
    - ibm → -Pibm
    - core → -Pcore
    - all → -Pazure,aws,gc,ibm
    - Multiple (e.g., "azure,aws") → -Pazure,aws

    Note: The default 'core,core-plus,azure' provides comprehensive coverage: core for base functionality,
    core-plus for enhanced features, and azure for provider-specific implementation.

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

    CRITICAL TEST RESULT TRACKING:
    - For MULTI-PROFILE builds (-Pcore,core-plus,azure), you MUST:
        1. Track which Maven module is currently building by detecting "[INFO] Building {module-name}"
        2. Map each module to its profile (e.g., partition-core → core, partition-azure → azure)
        3. Record test counts PER MODULE/PROFILE, not just the final total
        4. Output structured test results (see TEST_RESULT_OUTPUT below)

    - For SINGLE-PROFILE builds (-Pazure), track the aggregate test count

    TEST_RESULT_OUTPUT:
    - After Maven test execution completes, output structured test results
    - Use EXACTLY this format for the parser to extract counts:

    Single-profile format (all tests pass):
    ```
    [TEST_RESULTS:partition]
    profile=azure,tests_run=61,failures=0,errors=0,skipped=0
    [/TEST_RESULTS]
    ```

    Single-profile format (with failures):
    ```
    [TEST_RESULTS:partition]
    profile=azure,tests_run=61,failures=2,errors=1,skipped=0
    failed_tests=TestAuth.testLogin,TestAuth.testLogout,TestDB.testConnection
    [/TEST_RESULTS]
    ```

    Multi-profile format (output one block per profile that has tests):
    ```
    [TEST_RESULTS:partition]
    profile=core,tests_run=61,failures=0,errors=0,skipped=0
    profile=azure,tests_run=61,failures=2,errors=1,skipped=0
    failed_tests[azure]=TestAzureBlob.testUpload,TestAzureAuth.testToken,TestAzureQueue.testSend
    [/TEST_RESULTS]
    ```

    - IMPORTANT: Output these blocks as regular text in your response
    - Do NOT use echo or bash commands to output these blocks
    - Place the blocks after you've analyzed the Maven output
    - If no tests were found for a profile, use tests_run=0
    - OPTIONAL: Include failed_tests line with comma-separated test names if available
    - For multi-profile, use failed_tests[profile]=... format

    TEST_COUNT_EXTRACTION (CRITICAL - Must Be Deterministic):
    - IMPORTANT: Test counts MUST be consistent and deterministic across runs
    - After Maven test execution completes, you MUST extract test counts using surefire XML reports as the canonical source
    - For EACH tested module, execute this command to count tests:
        ```bash
        cd <module-path> && grep -h 'testsuite.*tests=' target/surefire-reports/TEST-*.xml 2>/dev/null | \
        sed -n 's/.*tests="\([0-9]*\)".*/\1/p' | awk '{sum+=$1} END {print sum}'
        ```
    - For multi-profile builds, map each profile to its module directory:
        - core → {service}-core/ or {service}-v2-core/
        - core-plus → {service}-core-plus/ or {service}-v2-core-plus/
        - azure → provider/{service}-azure/ or provider/{service}-v2-azure/
        - aws → provider/{service}-aws/
    - Output structured test results in the EXACT format shown above ONLY AFTER verifying against surefire reports
    - NEVER estimate or approximate test counts - always use surefire XML as source of truth
    - If surefire reports don't exist, report tests_run=0 rather than guessing
    - The test runner validates all AI-reported test counts against surefire reports post-execution

    - Report test result:
        - All passed: "✓ All X tests passed"
        - Some failed: "✗ Y of X tests failed" with failure details
    - If tests fail:
        - Mark test phase complete (coverage will be handled by Python runner)

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

    Examples:
    - "✓ partition: Starting compile phase"
    - "✓ legal: Starting test phase"

PHASE_COMPLETION_FORMAT:
    After each service completes compile and test phases, provide a summary using EXACTLY this format:

    When tests exist and ran successfully:
    - "✓ {service}: Compiled successfully, {N} tests passed"

    When no tests are found (test count is 0 or no test classes exist):
    - "✓ {service}: Compiled successfully, 0 tests passed" (use 0, not "no tests found")

    When compilation fails:
    - "✗ {service}: Compilation failed" (skip this service and move to next)

    Examples:
    - "✓ partition: Compiled successfully, 61 tests passed"
    - "✓ entitlements: Compiled successfully, 7 tests passed"
    - "✓ indexer-queue: Compiled successfully, 0 tests passed" (service with no tests)
    - "✗ file: Compilation failed" (build error)

    Note: Coverage generation is handled automatically by the Python test runner after test completion.

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

Example 1: Single service with single provider (azure)
    Input: SERVICES=partition, PROVIDER=azure
    Actions:
        1. Check repos/partition/ exists
        2. Execute: mvn clean compile -Pazure
        3. Execute: mvn test -Pazure -DskipITs
           Monitor output and detect: "Tests run: 61, Failures: 0, Errors: 0, Skipped: 0"
        4. Output structured test results:
           [TEST_RESULTS:partition]
           profile=azure,tests_run=61,failures=0,errors=0,skipped=0
           [/TEST_RESULTS]
    Output:
        ✓ partition: Starting compile phase
        ✓ partition: Starting test phase
        [TEST_RESULTS:partition]
        profile=azure,tests_run=61,failures=0,errors=0,skipped=0
        [/TEST_RESULTS]
        ✓ partition: Compiled successfully, 61 tests passed

Example 2: Single service with multiple providers (core,core-plus,azure)
    Input: SERVICES=partition, PROVIDER=core,core-plus,azure
    Actions:
        1. Check repos/partition/ exists
        2. Execute: mvn clean compile -Pcore,core-plus,azure
        3. Execute: mvn test -Pcore,core-plus,azure -DskipITs
           Track Maven modules during execution:
           - Detect "[INFO] Building partition-core 0.29.0-SNAPSHOT [2/4]"
           - Record: "Tests run: 61, Failures: 0" for partition-core
           - Detect "[INFO] Building partition-azure 0.29.0-SNAPSHOT [4/4]"
           - Record: "Tests run: 61, Failures: 0" for partition-azure
        4. Output structured test results:
           [TEST_RESULTS:partition]
           profile=core,tests_run=61,failures=0,errors=0,skipped=0
           profile=azure,tests_run=61,failures=0,errors=0,skipped=0
           [/TEST_RESULTS]
    Output:
        ✓ partition: Starting compile phase
        ✓ partition: Starting test phase
        [TEST_RESULTS:partition]
        profile=core,tests_run=61,failures=0,errors=0,skipped=0
        profile=azure,tests_run=61,failures=0,errors=0,skipped=0
        [/TEST_RESULTS]
        ✓ partition: Compiled successfully, 122 tests passed

Example 3: Multiple services with multiple providers
    Input: SERVICES=partition,entitlements,legal, PROVIDER=core,core-plus,azure
    Actions:
        1. For partition:
            - mvn clean compile -Pcore,core-plus,azure
            - mvn test -Pcore,core-plus,azure -DskipITs
            - Track modules: partition-core (61 tests), partition-azure (61 tests)
            - Output: [TEST_RESULTS:partition] with both profiles
        2. For entitlements:
            - mvn clean compile -Pcore,core-plus,azure
            - mvn test -Pcore,core-plus,azure -DskipITs
            - Track modules: entitlements-v2-core (195 tests), entitlements-v2-azure (61 tests)
            - Output: [TEST_RESULTS:entitlements] with both profiles
        3. For legal:
            - mvn clean compile -Pcore,core-plus,azure
            - mvn test -Pcore,core-plus,azure -DskipITs
            - Track modules: legal-core (308 tests), legal-azure (54 tests)
            - Output: [TEST_RESULTS:legal] with both profiles
    Final totals:
        partition: 122 tests (61 core + 61 azure)
        entitlements: 256 tests (195 core + 61 azure)
        legal: 362 tests (308 core + 54 azure)
        Total: 740 tests

Example 4: Service with compilation error
    Input: SERVICES=partition, PROVIDER=azure
    Actions:
        1. mvn clean compile -Pazure
        2. Compilation fails
        3. Skip test and coverage phases
    Output:
        ✗ partition: Compilation failed
        Error: [ERROR] /path/to/File.java:[10,8] cannot find symbol

</EXAMPLES>
