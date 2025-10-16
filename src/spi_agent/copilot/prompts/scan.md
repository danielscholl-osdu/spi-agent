Execute a complete Maven dependency and vulnerability triage for the {{SERVICE}} service.

**ACTION REQUIRED - DO NOT ASK FOR CONFIRMATION:**

Call scan_java_project_tool with these parameters:
- workspace: "{{WORKSPACE}}"
- scan_all_modules: true
- max_results: 100

**IMPORTANT PARAMETER NOTES:**
DO NOT add include_profiles or severity_filter parameters - they are currently broken due to a FastMCP schema bug and will cause validation errors. Our normalizer will automatically remove them if the LLM tries to add them.

The server will scan ALL modules/profiles and ALL severity levels by default. This provides comprehensive data for analysis and comparison.

**WHAT THE SCAN DOES:**
- Scans all Maven modules in the project (no profile filtering needed)
- Includes all severity levels: CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN
- Returns per-module vulnerability breakdown in module_summary
- Returns affected_modules sorted by severity (worst first)
- Uses Trivy for vulnerability detection

**EXPECTED SCAN TIME:** ~30-60s depending on project size

**YOUR RESPONSE MUST START WITH THIS EXACT FORMAT (for parsing):**

```
SCAN_SUMMARY:
Total: Critical=<number>, High=<number>, Medium=<number>, Low=<number>

MODULE_BREAKDOWN:
core|<critical>|<high>|<medium>
core-plus|<critical>|<high>|<medium>
aws|<critical>|<high>|<medium>
azure|<critical>|<high>|<medium>
gc|<critical>|<high>|<medium>
ibm|<critical>|<high>|<medium>
testing|<critical>|<high>|<medium>
END_MODULE_BREAKDOWN
```

Use the module_summary field from scan results to extract per-module counts. If module_summary is not in the result, aggregate by parsing source_location from vulnerabilities array.

Provider names should be lowercase: core, core-plus, aws, azure, gc, ibm, testing

After the structured header, provide:

**Detailed Analysis:**

1. **Top 5 Critical/High Vulnerabilities**
   - CVE ID
   - Affected package (groupId:artifactId)
   - Installed version
   - Severity level
   - Recommended fix/upgrade version
   - Brief description of the vulnerability

4. **Remediation Recommendations** (prioritized)
   - What should be fixed first (critical issues)
   - Which modules need the most attention
   - Any common dependencies appearing across modules
   - Estimated effort/complexity

**PROVIDER COMPARISON FORMAT:**
When analyzing results, show a comparison like:
```
Provider Vulnerability Comparison:
- AWS:   5 vulnerabilities (0 critical, 1 high, 3 medium)
- Azure: 10 vulnerabilities (0 critical, 4 high, 5 medium)
- GC:    6 vulnerabilities (0 critical, 2 high, 4 medium)
- IBM:   13 vulnerabilities (0 critical, 5 high, 6 medium)

Ranking: AWS (best) → GC → Azure → IBM (worst)
```

**DO NOT:**
- Ask me which option to choose
- Wait for confirmation
- Show me the triage template
- Retry with different parameters if the first call works

**EXECUTE THE SCAN NOW** and return the actual vulnerability findings with comprehensive module-level analysis.
