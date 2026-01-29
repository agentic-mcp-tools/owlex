# Owlex Skills for Claude Code

These skills provide slash commands for invoking owlex agents from Claude Code.

## Installation

Copy the skill directories to your Claude Code skills folder:

```bash
cp -r skills/* ~/.claude/skills/
```

## Available Skills

| Skill | Description |
|-------|-------------|
| `/council` | Consult the AI council (Codex + Gemini + OpenCode + Grok) with 2-round deliberation |
| `/codex` | Start an OpenAI Codex CLI session for deep reasoning |
| `/gemini` | Start a Google Gemini CLI session with 1M context |
| `/critique` | Council critique mode - agents find bugs and flaws |
| `/liza` | Peer-reviewed coding - Claude implements, Codex/Gemini/Grok review with binding verdicts |

## Usage

### Council Skills

All council skills are **non-blocking** - they start the task and return immediately with a task_id.

```bash
/council How should I structure this auth system?
# Returns: Council started (task: abc-123...)

# Check results later:
mcp__owlex__get_task_result task_id=abc-123...
```

### Liza Skill

Liza is a peer-review loop:

```bash
/liza Add rate limiting to the login endpoint

# Claude implements, then:
liza_submit(task_id, "Added rate limiting with Redis...")

# Reviewers examine, provide feedback
# Loop until all approve
```

## Requirements

- Claude Code with owlex MCP server configured
- Codex CLI, Gemini CLI, and/or OpenCode installed (depending on which agents you want)
- For Grok: `XAI_API_KEY` environment variable
