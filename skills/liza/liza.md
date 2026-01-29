# Liza Skill - Peer-Supervised Coding

<skill-context>
Liza is a peer-supervised coding system where Claude (coder) implements tasks and external agents (Codex, Gemini) review with binding verdicts. Based on https://github.com/liza-mas/liza.

Use this skill when:
- User wants rigorous code review before completion
- User says "liza", "peer review", "external review", "adversarial review"
- User wants multiple AI perspectives on implementation quality
- User wants to ensure code is production-ready
</skill-context>

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Claude Code                               │
│         Orchestrator + CODER (trusted implementer)           │
└─────────────────────────────────────────────────────────────┘
                              │
                    [implementation]
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    ┌───────────┐        ┌──────────┐        ┌──────────┐
    │   Codex   │        │  Gemini  │        │ OpenCode │
    │ (Reviewer)│        │(Reviewer)│        │(Reviewer)│
    └───────────┘        └──────────┘        └──────────┘
```

## Workflow

### Step 1: Start Task

```
Use mcp__owlex__liza_start to create the task:

Parameters:
- task_description: What to implement
- reviewers: ["codex", "gemini"] (default)
- max_iterations: 5 (default)
- done_when: Optional completion criteria
```

### Step 2: Implement

Claude implements the task using standard tools (Write, Edit, Bash).
Follow the Coder Contract:
- No fabrication - don't claim to have done something you haven't
- No test corruption - never modify tests to make failing code pass
- No scope creep - only implement what was requested
- Be honest about assumptions and limitations

### Step 3: Submit for Review

```
Use mcp__owlex__liza_submit:

Parameters:
- task_id: From liza_start
- implementation_summary: Description of what you implemented
```

Reviewers will examine and return:
- **APPROVE**: Code meets requirements, no blocking issues
- **REJECT**: Issues found that must be fixed + specific feedback

### Step 4: Handle Verdict

**If ALL APPROVE:**
- Task complete! Celebrate.

**If ANY REJECT:**
1. Read the merged feedback carefully
2. Fix the identified issues
3. Do NOT introduce unrelated changes
4. Call liza_submit again with updated summary
5. Repeat until approved or max iterations

## Key Principles

### External Validation
Claude cannot self-approve. Reviewers provide binding verdicts.
This prevents:
- Sycophancy
- Phantom fixes
- Hallucinated completions
- Self-certification bias

### Critique Mode
Reviewers actively look for:
- Security vulnerabilities
- Race conditions
- Resource leaks
- Unhandled edge cases
- Missing validation
- Incorrect error handling

### Multi-Reviewer Benefit
Different reviewers catch different issues:
- Codex: Deep code analysis, bug finding
- Gemini: Architecture, patterns, large-scale issues
- OpenCode: Alternative perspective, edge cases

## Example Session

```
User: /liza Add rate limiting to the login endpoint

Claude: I'll create a Liza task for this.

[Calls liza_start with task_description]
→ Returns task_id: "task-1"

Claude: Now implementing rate limiting...

[Uses Write/Edit to add rate limiting code]

Claude: Implementation complete. Submitting for review.

[Calls liza_submit with implementation_summary]
→ Codex: REJECT - "Missing IP-based limiting, only user-based"
→ Gemini: REJECT - "No Redis backend for distributed systems"

Claude: I see the issues. Let me fix them.

[Fixes the implementation]

[Calls liza_submit again]
→ Codex: APPROVE
→ Gemini: APPROVE

Claude: All reviewers approved! Rate limiting is now implemented with:
- User-based rate limiting
- IP-based rate limiting
- Redis backend for distributed systems
```

## MCP Tools Reference

| Tool | Description |
|------|-------------|
| `liza_start` | Create a task for Claude to implement |
| `liza_submit` | Submit implementation for review |
| `liza_status` | Get current task status |
| `liza_feedback` | Get formatted feedback to address |

## Blackboard

State persisted in `.owlex/liza-state.yaml`:
- Task lifecycle tracking
- Review history
- Iteration count
- Merged feedback

View with: `owlex://liza/blackboard` resource

## Configuration

Default reviewers: `["codex", "gemini"]`
Default max iterations: 5
Critique mode: enabled (reviewers actively find issues)
Require all approve: true (all reviewers must approve)
