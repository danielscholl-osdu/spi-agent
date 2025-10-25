# Execution Display Feature

## Overview

Real-time, hierarchical visualization of agent execution with Betty-themed minimal symbols and configurable verbosity levels.

## Display Modes

### MINIMAL (Default - Results Focused)
**Philosophy**: Results matter, insights are optional.

**Interactive Chat Mode:**
```
◉ Agent (Betty)

> What version of os-core-lib-azure...

● Phase 3: search_in_files
   └─ → search_in_files (running...)

2/5 phases complete
```

**After completion:**
```
◎ Complete (61.8s) - 5 phases
```

**When to use**: Default for interactive chat mode - shows only what's actively happening.

---

### VERBOSE (Full Details)
**Philosophy**: Show everything for debugging and transparency.

**With `--verbose` flag:**
```
• Phase 1: find_dependency_versions (5.9s)
├── • Thinking (2 messages) - Response received (4.97s)
└── • → find_dependency_versions - No references found (1.02s)

• Phase 2: search_in_files (7.2s)
├── • Thinking (4 messages) - Response received (6.34s)
└── • → search_in_files - Found 1552 match(es) (0.82s)

● Phase 3: search_in_files (in progress, 3.1s)
├── • Thinking (6 messages) - Response received (4.69s)
└── → search_in_files (running...)
```

**When to use**: Debugging, understanding agent behavior, troubleshooting issues.

---

### QUIET (No Display)
**With `--quiet` flag:**
```
(no display at all - just results)
```

**When to use**: Scripting, CI/CD, when output needs to be machine-parseable.

---

## Symbol Set (Betty-Themed Minimal)

| Symbol | Meaning | Color | Usage |
|--------|---------|-------|-------|
| ◉ | Query/Session | cyan | Top-level indicator (Betty's eye) |
| ● | Active/Running | yellow | Current phase or tool |
| • | Completed | dim white | Finished items |
| → | Tool Executing | yellow | Active tool call |
| ◎ | Success/Complete | green | Session complete |
| ✗ | Error | red | Failed operation |
| ├── | Tree Branch | dim | Hierarchy connector |
| └─ | Tree Branch End | dim | Last child connector |

**Design Philosophy:**
- No emojis (requested by user)
- Minimal visual noise
- Betty theme (◉ from [◉‿◉])
- Color provides status without clutter
- Unicode symbols work in most terminals

---

## Key Improvements

### Before (Original)
```
⎿ 🤖 Thinking with AI (2 messages) - Response received (4.58s)
⎿ 🔧 find_dependency_versions - No references found for org.opengroup.osdu:os-core-lib-azure in POM files under repos (filtered by p... (0.61s)
⎿ 🤖 Thinking with AI (4 messages) - Response received (3.65s)
⎿ 🔧 search_in_files - Found 7 match(es) for 'os-core-lib-azure':
⎿ 🤖 Thinking with AI (6 messages) - Response received (4.69s)
... [13 total root nodes, displayed twice]
```

**Issues:**
- 13 flat root nodes
- Emoji clutter (🤖🔧)
- No hierarchy
- Duplicate display
- Truncated summaries
- Can't see progress at a glance

### After (Improved)
```
• Phase 1: find_dependency_versions (5.9s)
• Phase 2: search_in_files (7.2s)
• Phase 3: find_dependency_versions (5.9s)
● Phase 4: Initial thinking (in progress, 20.3s)
```

**Improvements:**
- 4 phases (69% reduction)
- Clean symbols (●•→)
- Clear hierarchy
- Single display
- Better summaries
- Progress visible

---

## Metrics

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Lines displayed | 26 | 4-8 | 70-85% reduction |
| Root nodes | 13 | 4 phases | 69% fewer items |
| Emojis | 26 | 0 | 100% cleaner |
| Duplicate display | Yes | No | Eliminated |
| Hierarchy depth | 1 level | 2 levels | Better context |
| User control | None | 3 modes | Flexible |

---

## Usage

### Interactive Chat
```bash
spi
> What version of os-core-lib-azure are we running?

# Shows MINIMAL mode by default (only active phase)
```

### Single Query - Default
```bash
spi -p "Read the file README.md"

# No display (results only)
```

### Single Query - Verbose
```bash
spi -p "What issues are open in partition?" --verbose

# Shows VERBOSE mode (all phases, all details)
```

### Single Query - Quiet
```bash
spi -p "List repositories" --quiet

# No headers, no display, just results
```

---

## Architecture

### Phase Detection
```
LLMRequestEvent (2 messages)
  → Create Phase 1
  → Set as current_phase

ToolStartEvent (read_file)
  → Add to current_phase.tool_nodes

ToolCompleteEvent (read_file)
  → Update node status

LLMRequestEvent (4 messages)
  → Complete Phase 1
  → Create Phase 2
  → Set as current_phase
```

### Rendering Flow
```
_render_tree()
  ↓
  Has phases? → _render_phases()
                  ↓
                  DisplayMode check:
                  - MINIMAL: Show only current phase
                  - DEFAULT: Show active + completed count
                  - VERBOSE: Show all phases expanded
```

---

## Configuration

Controlled by `DisplayMode` enum:
```python
class DisplayMode(Enum):
    MINIMAL = "minimal"    # Default: results-focused
    DEFAULT = "default"    # Show more context
    VERBOSE = "verbose"    # Show everything
```

Set via CLI flags:
- No flag = No display (single query mode)
- Interactive mode = MINIMAL by default
- `--verbose` = VERBOSE mode
- `--quiet` = No display

---

## Future Enhancements

Potential improvements if needed:
1. **Keyboard controls**: Press 'e' to expand, 'c' to collapse
2. **Configurable default**: User preference for default display mode
3. **Export trace**: Save execution to JSON for debugging
4. **Phase naming**: Auto-detect phase purpose (e.g., "Searching dependencies")
5. **DEFAULT mode**: Add middle-ground between MINIMAL and VERBOSE

---

## Testing

Run tests:
```bash
# All display tests
uv run pytest tests/test_display*.py tests/test_execution*.py -v

# Specific to execution tree
uv run pytest tests/test_execution_tree.py -v
```

Test coverage:
- Phase creation and grouping
- Display mode switching
- Symbol validation (no emojis)
- Event handling
- Auto-collapse behavior

---

## Technical Details

### Files Modified
- `src/spi_agent/display/execution_tree.py` - Core rendering logic
- `src/spi_agent/display/__init__.py` - Export DisplayMode
- `src/spi_agent/display/result_formatter.py` - Better tool summaries
- `src/spi_agent/cli.py` - Wire up display modes
- `tests/test_execution_tree.py` - Comprehensive tests

### Key Classes
- `ExecutionPhase` - Groups LLM + tools into logical phases
- `DisplayMode` - Controls verbosity level
- `ExecutionTreeDisplay` - Renders phase-based tree

### Dependencies
- No new dependencies required
- Uses existing `rich` library
- Backward compatible with all existing code
