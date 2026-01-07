# Owlex

[![Version](https://img.shields.io/github/v/release/agentic-mcp-tools/owlex)](https://github.com/agentic-mcp-tools/owlex/releases)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-compatible-purple)](https://modelcontextprotocol.io)

**Get a second opinion without leaving Claude Code.**

Different AI models have different strengths and blind spots. Owlex lets you query Codex, Gemini, and OpenCode directly from Claude Code - and optionally run a structured deliberation where they review each other's answers before Claude synthesizes a final response.

![Async council demo](media/owlex_async_demo.gif)

## How the Council Works

1. **Round 1** - Your question goes to each agent independently. They answer without seeing each other.
2. **Round 2** - Each agent sees all Round 1 answers and can revise their position.
3. **Synthesis** - Claude reviews everything and outputs a structured answer.

Use it for architecture decisions, debugging tricky issues, or when you want more confidence than a single model provides. Not for every question - for the ones that matter.

## Installation

```bash
uv tool install git+https://github.com/agentic-mcp-tools/owlex.git
```

Add to `.mcp.json`:

```json
{
  "mcpServers": {
    "owlex": {
      "command": "owlex-server"
    }
  }
}
```

## Usage

### Council Deliberation

```
council_ask prompt="Should I use a monorepo or multiple repos for 5 microservices?"
```

Options:
- `claude_opinion` - Share your initial thinking with agents
- `deliberate` - Enable Round 2 revision (default: true)
- `critique` - Agents critique each other instead of revise
- `timeout` - Timeout per agent in seconds (default: 300)

### Individual Agent Sessions

| Tool | Description |
|------|-------------|
| `start_codex_session` | New Codex session |
| `resume_codex_session` | Resume with session ID or `--last` |
| `start_gemini_session` | New Gemini session |
| `resume_gemini_session` | Resume with index or `latest` |

### Async Task Management

Council runs in the background. Start a query, keep working, check results later.

| Tool | Description |
|------|-------------|
| `wait_for_task` | Block until task completes |
| `get_task_result` | Check result without blocking |
| `list_tasks` | List tasks with status filter |
| `cancel_task` | Kill running task |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `COUNCIL_EXCLUDE_AGENTS` | `` | Skip agents (e.g., `opencode,gemini`) |
| `OWLEX_DEFAULT_TIMEOUT` | `300` | Timeout in seconds |
| `CODEX_BYPASS_APPROVALS` | `false` | Bypass sandbox (use with caution) |
| `GEMINI_YOLO_MODE` | `false` | Auto-approve Gemini actions |
| `OPENCODE_AGENT` | `plan` | `plan` (read-only) or `build` |

## Cost Notes

- **Codex** and **Gemini** use your existing subscriptions (Claude Max, Google AI Pro, etc.)
- **OpenCode** uses API tokens
- Exclude agents with `COUNCIL_EXCLUDE_AGENTS` to control costs
- Use council for important decisions, not every question

## When to Use Each Agent

| Agent | Strengths |
|-------|-----------|
| **Codex (gpt5.2-codex)** | Deep reasoning, code review, bug finding |
| **Gemini** | 1M context window, multimodal, large codebases |
| **OpenCode** | Alternative perspective, configurable models |
| **Claude** | Complex multi-step implementation, synthesis |
