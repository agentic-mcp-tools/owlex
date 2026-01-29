"""
Review Protocol - Structured verdict format for Liza reviews.

Defines the protocol for reviewers to communicate verdicts and feedback.
Provides parsing utilities to extract structured data from reviewer responses.
"""

import re
from dataclasses import dataclass
from enum import Enum


class VerdictStatus(str, Enum):
    """Possible review verdicts."""
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    BLOCKED = "BLOCKED"  # Reviewer cannot proceed (needs clarification)


@dataclass
class ReviewVerdict:
    """Parsed review verdict."""
    status: VerdictStatus
    feedback: str | None
    issues: list[str]  # Individual issues extracted
    raw_response: str
    confidence: float  # 0-1, how confident we are in the parse

    @property
    def approved(self) -> bool:
        return self.status == VerdictStatus.APPROVE


# Regex patterns for verdict extraction
VERDICT_PATTERNS = [
    # XML-style tags (preferred)
    r"<verdict>\s*(APPROVE|REJECT|BLOCKED)\s*</verdict>",
    # Markdown headers
    r"##?\s*Verdict:?\s*(APPROVE|REJECT|BLOCKED)",
    # Bold text
    r"\*\*Verdict:?\*\*\s*(APPROVE|REJECT|BLOCKED)",
    # Plain text patterns
    r"(?:^|\n)Verdict:?\s*(APPROVE|REJECT|BLOCKED)",
    r"(?:^|\n)(?:My |Final )?(?:verdict|decision):?\s*(APPROVE|REJECT|BLOCKED)",
    # Implicit patterns (lower confidence)
    r"I\s+(?:would\s+)?(?:recommend\s+)?(approve|reject)",
    r"This\s+(?:implementation\s+)?(?:is\s+)?(approved|rejected)",
]

FEEDBACK_PATTERNS = [
    # XML-style tags (preferred)
    r"<feedback>(.*?)</feedback>",
    r"<issues>(.*?)</issues>",
    # Markdown sections
    r"##?\s*Feedback:?\s*\n(.*?)(?=\n##|\n\*\*|$)",
    r"##?\s*Issues:?\s*\n(.*?)(?=\n##|\n\*\*|$)",
    # Bold headers
    r"\*\*Feedback:?\*\*\s*\n?(.*?)(?=\n\*\*|$)",
    r"\*\*Issues:?\*\*\s*\n?(.*?)(?=\n\*\*|$)",
]

ISSUE_PATTERNS = [
    # Bulleted lists
    r"[-*]\s+(.+?)(?=\n[-*]|\n\n|$)",
    # Numbered lists
    r"\d+[.)]\s+(.+?)(?=\n\d+[.)]|\n\n|$)",
]


def parse_verdict(response: str) -> ReviewVerdict:
    """
    Parse a reviewer's response into a structured verdict.

    Attempts to extract:
    - Verdict status (APPROVE/REJECT/BLOCKED)
    - Feedback text
    - Individual issues

    Args:
        response: Raw response text from reviewer

    Returns:
        ReviewVerdict with parsed data
    """
    response_lower = response.lower()
    status = None
    confidence = 0.0

    # Try verdict patterns in order of specificity
    for i, pattern in enumerate(VERDICT_PATTERNS):
        match = re.search(pattern, response, re.IGNORECASE | re.MULTILINE)
        if match:
            verdict_text = match.group(1).upper()
            if verdict_text in ("APPROVE", "APPROVED"):
                status = VerdictStatus.APPROVE
            elif verdict_text in ("REJECT", "REJECTED"):
                status = VerdictStatus.REJECT
            elif verdict_text == "BLOCKED":
                status = VerdictStatus.BLOCKED

            # Earlier patterns are more explicit = higher confidence
            confidence = 1.0 - (i * 0.1)
            confidence = max(confidence, 0.5)
            break

    # Fallback: infer from content
    if status is None:
        # Check for approval signals
        approve_signals = [
            "looks good", "lgtm", "ship it", "approved",
            "no issues", "well done", "excellent", "ready to merge",
        ]
        reject_signals = [
            "needs work", "please fix", "issues found", "rejected",
            "problems", "bugs", "vulnerabilities", "missing",
        ]

        approve_count = sum(1 for s in approve_signals if s in response_lower)
        reject_count = sum(1 for s in reject_signals if s in response_lower)

        if approve_count > reject_count and approve_count > 0:
            status = VerdictStatus.APPROVE
            confidence = 0.3 + (0.1 * approve_count)
        elif reject_count > 0:
            status = VerdictStatus.REJECT
            confidence = 0.3 + (0.1 * reject_count)
        else:
            # Default to REJECT if unclear (safe default)
            status = VerdictStatus.REJECT
            confidence = 0.1

    # Extract feedback
    feedback = None
    for pattern in FEEDBACK_PATTERNS:
        match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
        if match:
            feedback = match.group(1).strip()
            break

    # If no explicit feedback section, use the whole response minus verdict
    if feedback is None and status == VerdictStatus.REJECT:
        # Remove the verdict line and use remaining as feedback
        feedback = response
        for pattern in VERDICT_PATTERNS[:4]:  # Only explicit patterns
            feedback = re.sub(pattern, "", feedback, flags=re.IGNORECASE | re.MULTILINE)
        feedback = feedback.strip()
        if len(feedback) < 10:
            feedback = None

    # Extract individual issues
    issues = []
    if feedback:
        for pattern in ISSUE_PATTERNS:
            matches = re.findall(pattern, feedback, re.MULTILINE)
            issues.extend(m.strip() for m in matches if m.strip())

    # Deduplicate issues
    issues = list(dict.fromkeys(issues))

    return ReviewVerdict(
        status=status,
        feedback=feedback,
        issues=issues,
        raw_response=response,
        confidence=confidence,
    )


def format_verdict_prompt(critique_mode: bool = True) -> str:
    """
    Generate prompt instructions for reviewers on verdict format.

    Args:
        critique_mode: If True, emphasize finding issues over being polite

    Returns:
        Prompt text to include in reviewer instructions
    """
    base = """
## Review Verdict Format

After examining the implementation, provide your verdict using this format:

<verdict>APPROVE or REJECT</verdict>

<feedback>
Your detailed feedback here. If rejecting, list specific issues:
- Issue 1: Description
- Issue 2: Description
</feedback>

**Verdict Guidelines:**
- APPROVE: Implementation meets requirements, no blocking issues
- REJECT: Implementation has issues that must be fixed before approval
"""

    if critique_mode:
        base += """
**Critique Mode Active:**
- Your job is to find bugs, security issues, and architectural flaws
- Do NOT be polite at the expense of thoroughness
- Missing edge cases, error handling, or tests are grounds for rejection
- If something could break in production, REJECT
- Only APPROVE if you would stake your reputation on this code
"""
    else:
        base += """
**Review Mode:**
- Focus on correctness and meeting requirements
- Minor style issues should not block approval
- Suggest improvements but only REJECT for functional issues
"""

    return base


def build_review_prompt(
    task_description: str,
    implementation_summary: str | None,
    previous_feedback: str | None = None,
    iteration: int = 0,
    critique_mode: bool = True,
) -> str:
    """
    Build the prompt for a reviewer agent.

    Args:
        task_description: What was supposed to be implemented
        implementation_summary: Summary of the implementation
        previous_feedback: Feedback from previous iteration (if any)
        iteration: Current iteration number
        critique_mode: Whether to use critique mode

    Returns:
        Complete prompt for the reviewer
    """
    prompt = f"""# Code Review Request

## Task
{task_description}

## Implementation Summary
{implementation_summary or "(No summary provided - examine the code directly)"}
"""

    if iteration > 0 and previous_feedback:
        prompt += f"""
## Previous Feedback (Iteration {iteration - 1})
The coder was asked to address these issues:
{previous_feedback}

Please verify whether these issues have been properly addressed.
"""

    prompt += format_verdict_prompt(critique_mode)

    return prompt
