"""
Prompt templates for council deliberation.
Centralized prompt management for consistency and testability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .roles import RoleDefinition


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
    opencode_answer: str | None = None,
    claude_answer: str | None = None,
    critique: bool = False,
    include_original: bool = False,
) -> str:
    """
    Build the deliberation prompt for round 2.

    By default, the original_prompt is NOT included because R2 agents resume from
    R1 sessions and already have the original question in their context.

    When include_original=True (used for exec fallback when session resume fails),
    the original prompt is included so the agent has full context.

    Args:
        original_prompt: The original question asked
        codex_answer: Codex's round 1 answer (optional if excluded)
        gemini_answer: Gemini's round 1 answer (optional if excluded)
        opencode_answer: OpenCode's round 1 answer (optional if excluded)
        claude_answer: Optional Claude opinion to include
        critique: If True, use critique mode prompts
        include_original: If True, include original_prompt in the output (for exec fallback)

    Returns:
        Complete deliberation prompt string
    """
    if critique:
        intro = DELIBERATION_INTRO_CRITIQUE
        instruction = DELIBERATION_INSTRUCTION_CRITIQUE
    else:
        intro = DELIBERATION_INTRO_REVISE
        instruction = DELIBERATION_INSTRUCTION_REVISE

    parts = [intro]

    # Include original prompt when exec fallback is used (agent has no R1 context)
    if include_original and original_prompt:
        parts.extend(["", "ORIGINAL QUESTION:", original_prompt])

    if claude_answer:
        parts.extend(["", "CLAUDE'S ANSWER:", claude_answer])

    if codex_answer:
        parts.extend(["", "CODEX'S ANSWER:", codex_answer])

    if gemini_answer:
        parts.extend(["", "GEMINI'S ANSWER:", gemini_answer])

    if opencode_answer:
        parts.extend(["", "OPENCODE'S ANSWER:", opencode_answer])

    parts.extend(["", instruction])

    return "\n".join(parts)


# === Role Injection Functions ===

def inject_role_prefix(prompt: str, role: RoleDefinition | None) -> str:
    """
    Inject role prefix into a prompt for Round 1.

    Args:
        prompt: The original prompt
        role: The role definition (None or neutral role = no injection)

    Returns:
        Prompt with role prefix prepended (or original if no role)
    """
    if role is None or not role.round_1_prefix:
        return prompt
    return f"{role.round_1_prefix}{prompt}"


def build_deliberation_prompt_with_role(
    original_prompt: str,
    role: RoleDefinition | None = None,
    codex_answer: str | None = None,
    gemini_answer: str | None = None,
    opencode_answer: str | None = None,
    claude_answer: str | None = None,
    critique: bool = False,
    include_original: bool = False,
) -> str:
    """
    Build the deliberation prompt for round 2 with role prefix.

    The role prefix is prepended to maintain the agent's perspective
    ("sticky role") during deliberation.

    Args:
        original_prompt: The original question
        role: The role definition for this agent (maintains perspective in R2)
        codex_answer: Codex's round 1 answer
        gemini_answer: Gemini's round 1 answer
        opencode_answer: OpenCode's round 1 answer
        claude_answer: Optional Claude opinion
        critique: If True, use critique mode prompts
        include_original: If True, include original_prompt (for exec fallback)

    Returns:
        Complete deliberation prompt with role prefix
    """
    # Build base deliberation prompt
    base_prompt = build_deliberation_prompt(
        original_prompt=original_prompt,
        codex_answer=codex_answer,
        gemini_answer=gemini_answer,
        opencode_answer=opencode_answer,
        claude_answer=claude_answer,
        critique=critique,
        include_original=include_original,
    )

    # Inject role prefix for R2 (sticky role)
    if role is None or not role.round_2_prefix:
        return base_prompt

    return f"{role.round_2_prefix}{base_prompt}"
