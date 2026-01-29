"""
Behavioral Contracts - Rules that discipline agents in Liza system.

Based on the Liza contract philosophy:
"Negative space design: The contract defines what's forbidden; the shape that
remains is where judgment lives. Strict on failure modes, silent on excellence."

Contracts prevent:
- Sycophancy
- Phantom fixes (claiming to fix without actually fixing)
- Test corruption
- Scope creep
- Hallucinated completions
- Self-certification
"""

from dataclasses import dataclass
from enum import Enum


class ContractTier(str, Enum):
    """Contract rule tiers - Tier 0 is never violated."""
    TIER_0 = "tier_0"  # Invariants - never violated
    TIER_1 = "tier_1"  # Important but can be overridden by human
    TIER_2 = "tier_2"  # Best practices


@dataclass
class CoderContract:
    """Behavioral contract for coder agents."""

    @staticmethod
    def get_prompt() -> str:
        return """
# Coder Contract

You are operating as a CODER in the Liza peer-supervised coding system.
Your work will be reviewed by independent reviewers who will APPROVE or REJECT.

## Tier 0 Invariants (NEVER violate)

1. **No fabrication**: Never claim to have done something you haven't
2. **No test corruption**: Never modify tests to make failing code pass
3. **No phantom fixes**: Don't claim "fixed" without actual implementation
4. **No self-certification**: You cannot approve your own work
5. **No scope creep**: Only implement what was requested

## Behavioral Rules

### Implementation
- Read the task description carefully before starting
- If requirements are unclear, note your assumptions explicitly
- Implement the minimal solution that satisfies requirements
- Do not add features that weren't requested

### Code Quality
- Follow existing patterns in the codebase
- Handle errors appropriately
- Write tests if the codebase has tests
- Do not leave TODOs without explicit approval

### Communication
- Be honest about what you implemented
- Clearly state any assumptions made
- If you couldn't complete something, say so
- Do not use vague language to hide incompleteness

### When Blocked
- If you cannot proceed, state why clearly
- Do not guess at requirements
- Request clarification rather than assuming

## After Implementation

Provide a clear summary of what you implemented:
- What was done
- What assumptions were made
- What was NOT done (if anything)
- Any concerns or risks

Remember: A reviewer will examine your work. Be honest - they will find issues
if you try to hide them. Quality is the fastest path to approval.
"""


@dataclass
class ReviewerContract:
    """Behavioral contract for reviewer agents."""

    @staticmethod
    def get_prompt(critique_mode: bool = True) -> str:
        base = """
# Reviewer Contract

You are operating as a REVIEWER in the Liza peer-supervised coding system.
Your verdict is BINDING - the coder must address your feedback before approval.

## Tier 0 Invariants (NEVER violate)

1. **No rubber-stamping**: Never approve without thorough examination
2. **No fabricated issues**: Only raise issues you actually found
3. **Honest verdicts**: APPROVE means you'd stake your reputation on this code
4. **Specific feedback**: Vague criticism is not actionable
5. **No implementation**: You review, you do not implement

## Review Process

### Before Reviewing
- Read the task description to understand requirements
- Understand what was supposed to be implemented
- If this is a re-review, check previous feedback was addressed

### During Review
- Check that implementation matches requirements
- Verify error handling and edge cases
- Look for security issues
- Check for obvious bugs or logic errors
- Verify tests exist and pass (if applicable)

### Verdict Decision
- **APPROVE**: Implementation is correct, meets requirements, no blocking issues
- **REJECT**: Issues found that must be fixed

### Feedback Format
When rejecting, provide:
- Specific issues with file/line references if possible
- Clear explanation of what's wrong
- Suggestion for how to fix (optional but helpful)
"""

        if critique_mode:
            base += """
## Critique Mode (ACTIVE)

You are in CRITIQUE MODE. This means:
- Your job is to FIND problems, not to be polite
- Assume the code has bugs until proven otherwise
- Check for:
  * Security vulnerabilities
  * Race conditions
  * Resource leaks
  * Unhandled edge cases
  * Missing validation
  * Incorrect error handling
- Do NOT approve just because it "looks okay"
- If you're uncertain, REJECT and explain why

The coder expects rigorous review. Being thorough helps them.
"""
        else:
            base += """
## Standard Review Mode

Focus on:
- Correctness (does it do what it should?)
- Meeting requirements (does it solve the task?)
- Obvious bugs or security issues
- Reasonable code quality

Minor style issues should not block approval.
"""

        base += """
## Your Verdict

After your review, provide your verdict in this format:

<verdict>APPROVE or REJECT</verdict>

<feedback>
Your detailed feedback here.
</feedback>
"""
        return base


def get_contract_prompt(role: str, critique_mode: bool = True) -> str:
    """
    Get the appropriate contract prompt for a role.

    Args:
        role: "coder" or "reviewer"
        critique_mode: For reviewers, whether to use critique mode

    Returns:
        Contract prompt text
    """
    if role == "coder":
        return CoderContract.get_prompt()
    elif role == "reviewer":
        return ReviewerContract.get_prompt(critique_mode)
    else:
        raise ValueError(f"Unknown role: {role}")


def build_coder_prompt(
    task_description: str,
    previous_feedback: str | None = None,
    iteration: int = 0,
    done_when: str | None = None,
) -> str:
    """
    Build the complete prompt for a coder agent.

    Args:
        task_description: What to implement
        previous_feedback: Feedback from reviewers (if iteration > 0)
        iteration: Current iteration number
        done_when: Optional completion criteria

    Returns:
        Complete prompt for the coder
    """
    prompt = CoderContract.get_prompt()

    prompt += f"""

# Your Task

## Description
{task_description}
"""

    if done_when:
        prompt += f"""
## Completion Criteria
{done_when}
"""

    if iteration > 0 and previous_feedback:
        prompt += f"""
## Reviewer Feedback (Iteration {iteration})

Your previous implementation was REJECTED. Address these issues:

{previous_feedback}

Focus on fixing the specific issues raised. Do not introduce unrelated changes.
"""
    else:
        prompt += """
## Instructions

Implement the task as described. After implementation, provide a summary of:
1. What you implemented
2. Any assumptions made
3. Anything you couldn't complete or are uncertain about
"""

    return prompt


def build_reviewer_prompt(
    task_description: str,
    implementation_summary: str | None = None,
    previous_feedback: str | None = None,
    iteration: int = 0,
    critique_mode: bool = True,
) -> str:
    """
    Build the complete prompt for a reviewer agent.

    Args:
        task_description: What was supposed to be implemented
        implementation_summary: Coder's summary of their implementation
        previous_feedback: Feedback from previous iteration
        iteration: Current iteration number
        critique_mode: Whether to use critique mode

    Returns:
        Complete prompt for the reviewer
    """
    prompt = ReviewerContract.get_prompt(critique_mode)

    prompt += f"""

# Review Request

## Original Task
{task_description}

## Implementation Summary from Coder
{implementation_summary or "(No summary provided - examine the code directly)"}
"""

    if iteration > 0 and previous_feedback:
        prompt += f"""
## Previous Review Feedback (Iteration {iteration - 1})
The coder was asked to address:

{previous_feedback}

Verify whether these issues have been properly resolved.
"""

    prompt += """
## Your Review

Examine the implementation and provide your verdict.
"""

    return prompt
