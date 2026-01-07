# Owlex

[![Version](https://img.shields.io/github/v/release/agentic-mcp-tools/owlex)](https://github.com/agentic-mcp-tools/owlex/releases)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-compatible-purple)](https://modelcontextprotocol.io)

MCP server for multi-agent orchestration. Run Codex, Gemini, and OpenCode from Claude Code.

## Features

- **Council deliberation** - Query all agents in parallel, with optional revision round
- **Session management** - Start fresh or resume with full context preserved
- **Async execution** - Tasks run in background with timeout control
- **Critique mode** - Agents find bugs and flaws in each other's answers

## Demo

[**Watch demo (7x speed, 30s)**](media/owlex_async_demo_7x.mp4) - Async council deliberation: start a query, continue working, check results later

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

## Tools

### `council_ask`

Query all agents and collect answers with optional deliberation.

```
prompt           - Question to send (required)
claude_opinion   - Your opinion to share with agents
deliberate       - Enable revision round (default: true)
critique         - Agents critique instead of revise (default: false)
timeout          - Timeout per agent in seconds (default: 300)
```

Returns `round_1` with initial answers, `round_2` with revisions (if enabled).

### Agent Sessions

| Tool | Description |
|------|-------------|
| `start_codex_session` | New Codex session |
| `resume_codex_session` | Resume with session ID or `--last` |
| `start_gemini_session` | New Gemini session |
| `resume_gemini_session` | Resume with index or `latest` |

### Task Management

| Tool | Description |
|------|-------------|
| `wait_for_task` | Block until task completes |
| `get_task_result` | Check result without blocking |
| `list_tasks` | List tasks with status filter |
| `cancel_task` | Kill running task |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CODEX_BYPASS_APPROVALS` | `false` | Bypass sandbox (dangerous) |
| `CODEX_ENABLE_SEARCH` | `true` | Enable web search |
| `GEMINI_YOLO_MODE` | `false` | Auto-approve actions |
| `OPENCODE_AGENT` | `plan` | Agent: `plan` (read-only) or `build` |
| `COUNCIL_EXCLUDE_AGENTS` | `` | Comma-separated agents to exclude |
| `OWLEX_DEFAULT_TIMEOUT` | `300` | Default timeout in seconds |

## When to Use Each Agent

| Agent | Best For |
|-------|----------|
| **Codex** | Code review, bug finding, PRD discussion |
| **Gemini** | Large codebase (1M context), multimodal |
| **OpenCode** | Alternative perspective, plan mode |
| **Claude** | Complex multi-step implementation |
