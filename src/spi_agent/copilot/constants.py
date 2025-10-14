"""Constants for OSDU SPI services."""

# Service definitions matching fork.md
SERVICES = {
    "partition": "Partition Service",
    "entitlements": "Entitlements Service",
    "legal": "Legal Service",
    "schema": "Schema Service",
    "file": "File Service",
    "storage": "Storage Service",
    "indexer": "Indexer Service",
    "indexer-queue": "Indexer Queue Service",
    "search": "Search Service",
    "workflow": "Workflow Service",
}

# Centralized icon definitions for status display
# Used across all trackers for consistent visual language
STATUS_ICONS = {
    "pending": "⏸",
    "running": "▶",
    "querying": "▶",
    "compiling": "▶",
    "testing": "▶",
    "coverage": "▶",
    "assessing": "▶",
    "waiting": "||",
    "success": "✓",
    "gathered": "✓",
    "compile_success": "✓",
    "test_success": "✓",
    "error": "✗",
    "compile_failed": "✗",
    "test_failed": "✗",
    "skipped": "⊘",
}
