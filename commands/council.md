---
description: "Get multiple AI perspectives via Council deliberation"
---

# Council

Get perspectives from multiple AI agents (Codex, Gemini, OpenCode) on a question or decision.

## Usage

When the user invokes `/council <question>`, follow these steps:

1. **Parse the question** from the user's prompt
2. **Form your initial opinion** on the question (this enriches deliberation)
3. **Call the council** using the Owlex MCP:

```python
mcp__owlex__council_ask(
    prompt="<user's question>",
    claude_opinion="<your initial take on the question>",
    working_directory="<current project path>",
    deliberate=True,
    timeout=300
)
```

4. **Wait for results**:
```python
mcp__owlex__wait_for_task(task_id="<from above>", timeout=300)
```

5. **Synthesize and present** the results:
   - Summarize areas of agreement
   - Highlight notable disagreements
   - Note unique insights from each agent
   - Provide your recommendation based on the council

## When to Use

- Architectural decisions with trade-offs
- Complex debugging needing multiple perspectives
- Design reviews
- Security audits (multiple eyes)
- Any decision where diverse viewpoints help

## Example

```
User: /council Should we use Redis or Postgres for our caching layer?

Claude:
1. Forms opinion: "Redis is better for pure caching due to speed"
2. Calls council_ask with the question and opinion
3. Waits for Codex, Gemini, OpenCode responses
4. Synthesizes: "Council agrees Redis for caching, but notes Postgres
   could work if you need persistence. Codex raised security concerns
   about Redis default config..."
```
