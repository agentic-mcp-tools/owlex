"""
Liza Orchestrator - Coordination for Claude (coder) + reviewer agents loop.

Architecture:
- Claude Code = Orchestrator + Coder (trusted, actually writes code)
- Codex/Gemini/OpenCode = Reviewers (via owlex MCP)

Flow:
1. Claude implements the task (using Write/Edit/Bash tools)
2. Claude sends implementation summary to reviewers via owlex
3. Reviewers examine and return APPROVE/REJECT + feedback
4. If REJECT: Claude fixes based on merged feedback, loop back
5. If APPROVE: done
"""

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Awaitable

from .blackboard import Blackboard, Task, TaskStatus
from .protocol import parse_verdict, VerdictStatus, ReviewVerdict
from .contracts import build_reviewer_prompt


def _log(msg: str):
    """Log to stderr."""
    print(f"[Liza] {msg}", file=sys.stderr, flush=True)


@dataclass
class LizaConfig:
    """Configuration for Liza orchestrator."""
    max_iterations: int = 5
    critique_mode: bool = True
    parallel_reviews: bool = True  # Run reviewers in parallel
    require_all_approve: bool = True  # All reviewers must approve
    timeout_per_agent: int = 300  # Seconds per reviewer call
    working_directory: str | None = None
    reviewers: list[str] = field(default_factory=lambda: ["codex", "gemini"])


@dataclass
class ReviewRoundResult:
    """Result of a single review round."""
    iteration: int
    reviews: dict[str, ReviewVerdict]  # reviewer -> verdict
    all_approved: bool
    merged_feedback: str | None
    issues_found: list[str]


@dataclass
class LizaResult:
    """Final result of a Liza session."""
    task_id: str
    task_description: str
    final_status: TaskStatus
    review_rounds: list[ReviewRoundResult]
    total_iterations: int
    approved: bool
    all_feedback: list[str]
    duration_seconds: float
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "task_description": self.task_description,
            "final_status": self.final_status.value,
            "total_iterations": self.total_iterations,
            "approved": self.approved,
            "all_feedback": self.all_feedback,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "review_rounds": [
                {
                    "iteration": rr.iteration,
                    "all_approved": rr.all_approved,
                    "merged_feedback": rr.merged_feedback,
                    "issues_found": rr.issues_found,
                    "reviews": {
                        reviewer: {
                            "status": v.status.value,
                            "feedback": v.feedback,
                            "issues": v.issues,
                            "confidence": v.confidence,
                        }
                        for reviewer, v in rr.reviews.items()
                    },
                }
                for rr in self.review_rounds
            ],
        }


# Type for reviewer runner function (calls owlex agents)
ReviewerRunner = Callable[[str, str, str | None, int], Awaitable[str | None]]


class LizaOrchestrator:
    """
    Orchestrates the Liza review loop.

    Claude Code is the coder (trusted implementer).
    Codex/Gemini/OpenCode are reviewers (via owlex MCP).

    This orchestrator:
    1. Manages the blackboard state
    2. Sends implementation to reviewers
    3. Parses verdicts and merges feedback
    4. Returns feedback to Claude for iteration

    Claude does the actual implementation outside this orchestrator.
    """

    def __init__(
        self,
        config: LizaConfig | None = None,
        blackboard: Blackboard | None = None,
    ):
        """
        Initialize orchestrator.

        Args:
            config: Liza configuration
            blackboard: Blackboard instance (creates one if not provided)
        """
        self.config = config or LizaConfig()
        self.blackboard = blackboard or Blackboard(self.config.working_directory)
        self._reviewer_runner: ReviewerRunner | None = None
        self.log_entries: list[str] = []

    def log(self, msg: str):
        """Add to log and print."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        self.log_entries.append(entry)
        _log(msg)

    def set_reviewer_runner(self, runner: ReviewerRunner):
        """
        Set the function that runs reviewer agents.

        The runner should have signature:
            async def run(agent: str, prompt: str, working_dir: str | None, timeout: int) -> str | None

        Where agent is "codex", "gemini", or "opencode".
        This will be connected to owlex's agent execution.
        """
        self._reviewer_runner = runner

    async def run_reviewer(
        self,
        agent: str,
        prompt: str,
    ) -> str | None:
        """Run a reviewer agent with the given prompt."""
        if self._reviewer_runner is None:
            raise RuntimeError("Reviewer runner not set. Call set_reviewer_runner first.")

        return await self._reviewer_runner(
            agent,
            prompt,
            self.config.working_directory,
            self.config.timeout_per_agent,
        )

    async def submit_for_review(
        self,
        task_id: str,
        implementation_summary: str,
    ) -> ReviewRoundResult:
        """
        Submit Claude's implementation for review by owlex agents.

        Args:
            task_id: Task being reviewed
            implementation_summary: Summary/description of what Claude implemented

        Returns:
            ReviewRoundResult with all verdicts and merged feedback
        """
        task = self.blackboard.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        # Update blackboard
        self.blackboard.submit_for_review(task_id, implementation_summary)
        self.blackboard.transition_task(task_id, TaskStatus.IN_REVIEW)

        reviewers = task.reviewers or self.config.reviewers
        self.log(f"Submitting to reviewers: {', '.join(reviewers)}")

        reviews: dict[str, ReviewVerdict] = {}

        if self.config.parallel_reviews:
            # Run reviewers in parallel
            review_tasks = []
            for reviewer in reviewers:
                review_tasks.append(
                    self._run_single_reviewer(task, reviewer, implementation_summary)
                )

            review_results = await asyncio.gather(*review_tasks, return_exceptions=True)

            for reviewer, result in zip(reviewers, review_results):
                if isinstance(result, Exception):
                    self.log(f"Reviewer {reviewer} failed: {result}")
                    reviews[reviewer] = ReviewVerdict(
                        status=VerdictStatus.BLOCKED,
                        feedback=f"Reviewer error: {result}",
                        issues=[],
                        raw_response="",
                        confidence=0,
                    )
                else:
                    reviews[reviewer] = result
        else:
            # Run reviewers sequentially
            for reviewer in reviewers:
                try:
                    verdict = await self._run_single_reviewer(task, reviewer, implementation_summary)
                    reviews[reviewer] = verdict
                except Exception as e:
                    self.log(f"Reviewer {reviewer} failed: {e}")
                    reviews[reviewer] = ReviewVerdict(
                        status=VerdictStatus.BLOCKED,
                        feedback=f"Reviewer error: {e}",
                        issues=[],
                        raw_response="",
                        confidence=0,
                    )

        # Record reviews in blackboard
        for reviewer, verdict in reviews.items():
            self.blackboard.record_review(
                task_id,
                reviewer=reviewer,
                verdict=verdict.status.value,
                feedback=verdict.feedback,
            )

        # Determine overall verdict
        if self.config.require_all_approve:
            all_approved = all(v.approved for v in reviews.values())
        else:
            # Majority vote
            approve_count = sum(1 for v in reviews.values() if v.approved)
            all_approved = approve_count > len(reviews) // 2

        # Collect all issues
        all_issues = []
        for verdict in reviews.values():
            all_issues.extend(verdict.issues)

        # Merge feedback from all reviewers (not just rejecting ones)
        feedback_parts = []
        for reviewer, verdict in reviews.items():
            status_emoji = "✅" if verdict.approved else "❌"
            feedback_parts.append(
                f"### {reviewer.title()} {status_emoji} ({verdict.status.value})\n"
                f"**Confidence:** {verdict.confidence:.0%}\n\n"
                f"{verdict.feedback or '(no detailed feedback)'}"
            )
        merged_feedback = "\n\n---\n\n".join(feedback_parts)

        # Log verdicts
        for reviewer, verdict in reviews.items():
            self.log(f"{reviewer}: {verdict.status.value} (confidence: {verdict.confidence:.0%})")

        # Update blackboard with final verdict
        task, _ = self.blackboard.finalize_reviews(task_id)

        result = ReviewRoundResult(
            iteration=task.iteration,
            reviews=reviews,
            all_approved=all_approved,
            merged_feedback=merged_feedback,
            issues_found=all_issues,
        )

        if all_approved:
            self.log(f"✅ All reviewers APPROVED")
        else:
            self.log(f"❌ Review REJECTED - {len(all_issues)} issues found")

        return result

    async def _run_single_reviewer(
        self,
        task: Task,
        reviewer: str,
        implementation_summary: str,
    ) -> ReviewVerdict:
        """Run a single reviewer and parse verdict."""
        self.log(f"Running reviewer: {reviewer}")

        reviewer_prompt = build_reviewer_prompt(
            task_description=task.description,
            implementation_summary=implementation_summary,
            previous_feedback=task.merged_feedback,
            iteration=task.iteration,
            critique_mode=self.config.critique_mode,
        )

        response = await self.run_reviewer(reviewer, reviewer_prompt)

        if response is None:
            return ReviewVerdict(
                status=VerdictStatus.BLOCKED,
                feedback="Reviewer failed to respond",
                issues=[],
                raw_response="",
                confidence=0,
            )

        verdict = parse_verdict(response)
        return verdict

    def prepare_for_iteration(self, task_id: str, merged_feedback: str) -> Task:
        """
        Prepare task for next iteration after rejection.

        Updates blackboard state for Claude to iterate.

        Args:
            task_id: Task to update
            merged_feedback: Combined feedback from reviewers

        Returns:
            Updated task
        """
        task = self.blackboard.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        task.iteration += 1
        task.merged_feedback = merged_feedback
        task.status = TaskStatus.WORKING
        task.add_history("iteration_started", agent="claude", details={
            "iteration": task.iteration,
        })

        self.blackboard.update_task(task)
        self.log(f"Prepared for iteration {task.iteration}")

        return task

    def mark_approved(self, task_id: str) -> Task:
        """Mark task as approved and complete."""
        return self.blackboard.transition_task(
            task_id, TaskStatus.APPROVED,
            agent="liza",
            details={"approved_by": "reviewers"},
        )

    def mark_blocked(self, task_id: str, reason: str) -> Task:
        """Mark task as blocked."""
        return self.blackboard.transition_task(
            task_id, TaskStatus.BLOCKED,
            details={"reason": reason},
        )

    # === Convenience methods for MCP tool ===

    def create_task(
        self,
        description: str,
        reviewers: list[str] | None = None,
        max_iterations: int | None = None,
        done_when: str | None = None,
    ) -> Task:
        """
        Create a new task for Claude to implement.

        Args:
            description: What to implement
            reviewers: Which agents review (default from config)
            max_iterations: Max review cycles (default from config)
            done_when: Completion criteria

        Returns:
            Created task
        """
        if not self.blackboard.exists():
            self.blackboard.initialize(goal=description[:100])

        task = self.blackboard.add_task(
            description=description,
            coder="claude",  # Claude is always the coder
            reviewers=reviewers or self.config.reviewers,
            max_iterations=max_iterations or self.config.max_iterations,
            done_when=done_when,
            status=TaskStatus.WORKING,  # Claude starts working immediately
        )

        # Claude claims the task
        task.add_history("claimed_by_claude")
        self.blackboard.update_task(task)

        self.log(f"Created task {task.id}: {description[:50]}...")
        return task

    def get_task_status(self, task_id: str) -> dict | None:
        """Get current task status for MCP response."""
        task = self.blackboard.get_task(task_id)
        if task is None:
            return None

        return {
            "task_id": task.id,
            "description": task.description,
            "status": task.status.value,
            "iteration": task.iteration,
            "max_iterations": task.max_iterations,
            "reviewers": task.reviewers,
            "merged_feedback": task.merged_feedback,
            "review_count": len(task.reviews),
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    def get_feedback_for_claude(self, task_id: str) -> str | None:
        """
        Get formatted feedback for Claude to address.

        Returns None if no feedback (approved or not yet reviewed).
        """
        task = self.blackboard.get_task(task_id)
        if task is None or task.merged_feedback is None:
            return None

        return f"""# Review Feedback (Iteration {task.iteration})

Your implementation was reviewed. Please address the following feedback:

{task.merged_feedback}

## Instructions
1. Read the feedback carefully
2. Fix the identified issues
3. Do NOT introduce unrelated changes
4. When done, call `liza_submit` with your implementation summary
"""
