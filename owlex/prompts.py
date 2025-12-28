"""
Prompt templates for council deliberation.
Centralized prompt management for consistency and testability.
"""

# === Round 2: Deliberation Prompts ===

DELIBERATION_INTRO_REVISE = (
    "You previously answered a question. Now review all council members' "
    "answers and provide your revised opinion."
)

DELIBERATION_INTRO_CRITIQUE = (
    "You previously answered a question. Now act as a senior code reviewer "
    "and critically analyze the other council members' answers."
)

DELIBERATION_INSTRUCTION_REVISE = (
    "Please provide your revised answer after considering the other perspectives. "
    "Note any points of agreement or disagreement."
)

DELIBERATION_INSTRUCTION_CRITIQUE = (
    "Act as a senior reviewer. Identify bugs, security vulnerabilities, "
    "architectural flaws, incorrect assumptions, or gaps in the other answers. "
    "Be specific and critical. For code suggestions, look for edge cases, "
    "error handling issues, and potential failures. Do not just agree - find problems."
)


def build_deliberation_prompt(
    original_prompt: str,
    codex_answer: str | None = None,
    gemini_answer: str | None = None,
    aider_answer: str | None = None,
    opencode_answer: str | None = None,
    claude_answer: str | None = None,
    critique: bool = False,
) -> str:
    """
    Build the deliberation prompt for round 2.

    Note: The original_prompt is kept as a parameter for backwards compatibility
    but is no longer included in the prompt. R2 agents resume from R1 sessions
    and already have the original question in their context.

    Args:
        original_prompt: The original question asked (unused, kept for API compat)
        codex_answer: Codex's round 1 answer (optional if excluded)
        gemini_answer: Gemini's round 1 answer (optional if excluded)
        aider_answer: Aider's round 1 answer (optional if excluded)
        opencode_answer: OpenCode's round 1 answer (optional if excluded)
        claude_answer: Optional Claude opinion to include
        critique: If True, use critique mode prompts

    Returns:
        Complete deliberation prompt string
    """
    if critique:
        intro = DELIBERATION_INTRO_CRITIQUE
        instruction = DELIBERATION_INSTRUCTION_CRITIQUE
    else:
        intro = DELIBERATION_INTRO_REVISE
        instruction = DELIBERATION_INSTRUCTION_REVISE

    # R2 agents resume from R1 sessions, so they already have the original
    # question in context. We only need to show other agents' answers.
    parts = [intro]

    if claude_answer:
        parts.extend(["", "CLAUDE'S ANSWER:", claude_answer])

    if aider_answer:
        parts.extend(["", "AIDER'S ANSWER:", aider_answer])

    if codex_answer:
        parts.extend(["", "CODEX'S ANSWER:", codex_answer])

    if gemini_answer:
        parts.extend(["", "GEMINI'S ANSWER:", gemini_answer])

    if opencode_answer:
        parts.extend(["", "OPENCODE'S ANSWER:", opencode_answer])

    parts.extend(["", instruction])

    return "\n".join(parts)
