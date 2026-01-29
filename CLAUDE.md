# Owlex - Claude Code Configuration

## Overview

Owlex is an MCP server that provides access to multiple AI agents (Codex, Gemini, OpenCode) from within Claude Code. It enables:

1. **Council Deliberation** - Get multiple AI perspectives with optional revision rounds
2. **Liza Peer Review** - Claude implements, external agents review with binding verdicts
3. **Individual Sessions** - Direct agent access with session persistence

## Quick Reference

### Council (Consultation)

```
/council "Your question here"
```

Or with tools:
```python
council_ask(
    prompt="Your question",
    team="security_audit",  # or roles=["security", "perf", "skeptic"]
    deliberate=True,
    critique=True,
)
```

### Liza (Peer-Reviewed Implementation)

```
/liza "Implement feature X"
```

**Flow:**
1. `liza_start` - Create task
2. Claude implements (Write/Edit/Bash)
3. `liza_submit` - Send for review
4. If REJECT → fix and resubmit
5. If ALL APPROVE → done

**Tools:**
| Tool | Purpose |
|------|---------|
| `liza_start` | Create implementation task |
| `liza_submit` | Submit for review |
| `liza_status` | Check task status |
| `liza_feedback` | Get reviewer feedback |

**Blackboard:** `.owlex/liza-state.yaml`

### Individual Agents

```python
# Codex
start_codex_session(prompt="...")
resume_codex_session(prompt="...", session_id="...")

# Gemini
start_gemini_session(prompt="...")
resume_gemini_session(prompt="...", session_ref="latest")

# OpenCode
start_opencode_session(prompt="...")
resume_opencode_session(prompt="...")
```

## When to Use What

| Scenario | Tool |
|----------|------|
| Need multiple opinions | `/council` |
| Production code with review | `/liza` |
| Deep code analysis | `start_codex_session` |
| Large codebase (1M tokens) | `start_gemini_session` |
| Alternative perspective | `start_opencode_session` |
| Architecture decisions | `council_ask team="architecture_review"` |
| Security review | `council_ask team="security_audit"` |

## Liza Architecture

```
Claude Code = Orchestrator + Coder (trusted)
Codex/Gemini/OpenCode = Reviewers (external validation)
```

**Key Principles:**
- Claude implements, cannot self-approve
- Reviewers provide binding APPROVE/REJECT verdicts
- Multiple reviewers catch different issues
- Iterate until all approve or max iterations

**Contract Rules (from Liza):**
- No fabrication - don't claim to have done something you haven't
- No test corruption - never modify tests to make failing code pass
- No scope creep - only implement what was requested
- Be honest about assumptions and limitations

## Configuration

Environment variables:
```bash
COUNCIL_EXCLUDE_AGENTS=""        # Skip agents: "opencode,gemini"
COUNCIL_DEFAULT_TEAM=""          # Default team preset
OWLEX_DEFAULT_TIMEOUT=300        # Timeout in seconds
CODEX_BYPASS_APPROVALS=false     # Bypass sandbox
GEMINI_YOLO_MODE=false           # Auto-approve actions
```

## Development

```bash
# Run tests
pytest tests/test_liza.py -v

# Install locally
pip install -e .

# Check module
python -c "from owlex.liza import LizaOrchestrator; print('OK')"
```

## File Structure

```
owlex/
├── server.py          # MCP server with all tools
├── council.py         # Council deliberation logic
├── engine.py          # Agent execution engine
├── liza/              # Liza peer-review system
│   ├── blackboard.py  # State management
│   ├── contracts.py   # Behavioral rules
│   ├── orchestrator.py # Review loop coordination
│   └── protocol.py    # Verdict parsing
├── skills/            # Slash command skills
│   ├── liza/          # /liza skill
│   └── council/       # /council skill
└── commands/          # Command documentation
    ├── liza.md
    └── council.md
```
