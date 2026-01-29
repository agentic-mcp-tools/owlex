# /liza - Peer-Reviewed Coding with External Validation

Start a Liza session where Claude implements and Codex/Gemini review.

## Usage

```
/liza <task description>
```

## Examples

```
/liza Add a login endpoint with rate limiting
/liza Fix the bug in the authentication flow
/liza Implement user profile page with avatar upload
```

## How It Works

**Architecture:**
- **Claude** = Coder (trusted, actually writes code)
- **Codex/Gemini** = Reviewers (examine and provide binding verdicts)

**Flow:**
1. `/liza` creates a task → Claude implements
2. Claude submits for review → Codex and Gemini examine
3. If REJECT: Claude fixes based on feedback, resubmits
4. If ALL APPROVE: Done!

## Key Principles (from Liza)

- **External validation**: Claude cannot self-approve; reviewers provide binding verdicts
- **Critique mode**: Reviewers actively look for bugs, security issues, edge cases
- **Iteration until approved**: Loop continues until all reviewers approve or max iterations
- **Merged feedback**: Different reviewers catch different issues

## MCP Tools

| Tool | Purpose |
|------|---------|
| `liza_start` | Create task (called by this command) |
| `liza_submit` | Submit implementation for review |
| `liza_status` | Check task status |
| `liza_feedback` | Get feedback to address |

## Blackboard

State is persisted in `.owlex/liza-state.yaml` for resumability.
View with resource: `owlex://liza/blackboard`
