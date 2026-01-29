"""
Blackboard - Shared state coordination for Liza multi-agent system.

The blackboard is the single source of truth for task state, assignments,
and history. All agents read from and write to this shared state.

State file location: .owlex/liza-state.yaml (in working directory)
"""

import os
import fcntl
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class TaskStatus(str, Enum):
    """Task lifecycle states."""
    DRAFT = "DRAFT"                     # Planner creating task
    UNCLAIMED = "UNCLAIMED"             # Ready to be claimed by coder
    CLAIMED = "CLAIMED"                 # Coder has claimed, not yet started
    WORKING = "WORKING"                 # Coder implementing
    READY_FOR_REVIEW = "READY_FOR_REVIEW"  # Submitted for review
    IN_REVIEW = "IN_REVIEW"             # Reviewer examining
    APPROVED = "APPROVED"               # Reviewer approved
    REJECTED = "REJECTED"               # Reviewer rejected (needs iteration)
    BLOCKED = "BLOCKED"                 # Cannot proceed without intervention
    SUPERSEDED = "SUPERSEDED"           # Replaced by another task
    MERGED = "MERGED"                   # Approved and merged


class AgentRole(str, Enum):
    """Agent roles in Liza system."""
    CODER = "coder"
    REVIEWER = "reviewer"
    PLANNER = "planner"


@dataclass
class HistoryEntry:
    """A single entry in task history."""
    time: str
    event: str
    agent: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        d = {"time": self.time, "event": self.event}
        if self.agent:
            d["agent"] = self.agent
        if self.details:
            d["details"] = self.details
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        return cls(
            time=data["time"],
            event=data["event"],
            agent=data.get("agent"),
            details=data.get("details"),
        )


@dataclass
class ReviewRecord:
    """Record of a single review."""
    reviewer: str
    verdict: str  # APPROVE or REJECT
    feedback: str | None
    timestamp: str
    iteration: int

    def to_dict(self) -> dict:
        return {
            "reviewer": self.reviewer,
            "verdict": self.verdict,
            "feedback": self.feedback,
            "timestamp": self.timestamp,
            "iteration": self.iteration,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewRecord":
        return cls(
            reviewer=data["reviewer"],
            verdict=data["verdict"],
            feedback=data.get("feedback"),
            timestamp=data["timestamp"],
            iteration=data["iteration"],
        )


@dataclass
class Task:
    """A task in the Liza system."""
    id: str
    description: str
    status: TaskStatus = TaskStatus.UNCLAIMED
    coder: str | None = None
    reviewers: list[str] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 5
    done_when: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    history: list[HistoryEntry] = field(default_factory=list)
    reviews: list[ReviewRecord] = field(default_factory=list)
    last_implementation: str | None = None  # Summary of last implementation
    merged_feedback: str | None = None  # Combined feedback from all reviewers

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "coder": self.coder,
            "reviewers": self.reviewers,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "done_when": self.done_when,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "history": [h.to_dict() for h in self.history],
            "reviews": [r.to_dict() for r in self.reviews],
            "last_implementation": self.last_implementation,
            "merged_feedback": self.merged_feedback,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(
            id=data["id"],
            description=data["description"],
            status=TaskStatus(data["status"]),
            coder=data.get("coder"),
            reviewers=data.get("reviewers", []),
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 5),
            done_when=data.get("done_when"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            history=[HistoryEntry.from_dict(h) for h in data.get("history", [])],
            reviews=[ReviewRecord.from_dict(r) for r in data.get("reviews", [])],
            last_implementation=data.get("last_implementation"),
            merged_feedback=data.get("merged_feedback"),
        )

    def add_history(self, event: str, agent: str | None = None, details: dict | None = None):
        """Add a history entry."""
        self.history.append(HistoryEntry(
            time=datetime.now(timezone.utc).isoformat(),
            event=event,
            agent=agent,
            details=details,
        ))
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_review(self, reviewer: str, verdict: str, feedback: str | None):
        """Add a review record."""
        self.reviews.append(ReviewRecord(
            reviewer=reviewer,
            verdict=verdict,
            feedback=feedback,
            timestamp=datetime.now(timezone.utc).isoformat(),
            iteration=self.iteration,
        ))
        self.updated_at = datetime.now(timezone.utc).isoformat()


@dataclass
class BlackboardState:
    """Full blackboard state."""
    version: int = 1
    goal: str = ""
    spec_ref: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tasks: list[Task] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "goal": self.goal,
            "spec_ref": self.spec_ref,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tasks": [t.to_dict() for t in self.tasks],
            "config": self.config,
            "log": self.log,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BlackboardState":
        return cls(
            version=data.get("version", 1),
            goal=data.get("goal", ""),
            spec_ref=data.get("spec_ref"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            tasks=[Task.from_dict(t) for t in data.get("tasks", [])],
            config=data.get("config", {}),
            log=data.get("log", []),
        )


class Blackboard:
    """
    Blackboard state manager with file-based persistence.

    Provides atomic read/write operations with file locking.
    """

    DEFAULT_DIR = ".owlex"
    DEFAULT_FILE = "liza-state.yaml"

    def __init__(self, working_directory: str | None = None):
        """
        Initialize blackboard.

        Args:
            working_directory: Directory containing .owlex/. Defaults to CWD.
        """
        if working_directory is None:
            working_directory = os.getcwd()
        self.working_directory = Path(working_directory)
        self.state_dir = self.working_directory / self.DEFAULT_DIR
        self.state_file = self.state_dir / self.DEFAULT_FILE
        self.lock_file = self.state_dir / f"{self.DEFAULT_FILE}.lock"

    def exists(self) -> bool:
        """Check if blackboard state file exists."""
        return self.state_file.exists()

    def initialize(
        self,
        goal: str,
        spec_ref: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> BlackboardState:
        """
        Initialize a new blackboard.

        Args:
            goal: The goal/objective for this Liza session
            spec_ref: Optional reference to specification file
            config: Optional configuration overrides

        Returns:
            The initialized BlackboardState
        """
        # Create directory if needed
        self.state_dir.mkdir(parents=True, exist_ok=True)

        state = BlackboardState(
            goal=goal,
            spec_ref=spec_ref,
            config=config or {},
        )
        state.log.append(f"Blackboard initialized: {goal}")

        self._write_state(state)
        return state

    def read(self) -> BlackboardState:
        """
        Read current blackboard state.

        Returns:
            Current BlackboardState

        Raises:
            FileNotFoundError: If blackboard not initialized
        """
        if not self.exists():
            raise FileNotFoundError(f"Blackboard not found at {self.state_file}. Run liza_start to create a task.")

        with open(self.state_file, "r") as f:
            # Acquire shared lock for reading
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                data = yaml.safe_load(f)
                return BlackboardState.from_dict(data)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def write(self, state: BlackboardState):
        """
        Write blackboard state atomically.

        Args:
            state: The state to write
        """
        self._write_state(state)

    def _write_state(self, state: BlackboardState):
        """Write state with exclusive lock."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        state.updated_at = datetime.now(timezone.utc).isoformat()

        # Write to temp file then rename for atomicity
        temp_file = self.state_file.with_suffix(".yaml.tmp")

        with open(temp_file, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yaml.dump(state.to_dict(), f, default_flow_style=False, sort_keys=False)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Atomic rename
        temp_file.rename(self.state_file)

    def add_task(
        self,
        description: str,
        coder: str | None = None,
        reviewers: list[str] | None = None,
        max_iterations: int = 5,
        done_when: str | None = None,
        status: TaskStatus = TaskStatus.UNCLAIMED,
    ) -> Task:
        """
        Add a new task to the blackboard.

        Args:
            description: Task description
            coder: Agent to implement (e.g., "codex")
            reviewers: Agents to review (e.g., ["gemini", "opencode"])
            max_iterations: Maximum coder-reviewer cycles
            done_when: Completion criteria
            status: Initial status (default UNCLAIMED)

        Returns:
            The created Task
        """
        state = self.read()

        task_id = f"task-{len(state.tasks) + 1}"
        task = Task(
            id=task_id,
            description=description,
            status=status,
            coder=coder,
            reviewers=reviewers or [],
            max_iterations=max_iterations,
            done_when=done_when,
        )
        task.add_history("task_created", details={"description": description[:100]})

        state.tasks.append(task)
        state.log.append(f"Task {task_id} created: {description[:50]}...")

        self.write(state)
        return task

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        state = self.read()
        for task in state.tasks:
            if task.id == task_id:
                return task
        return None

    def update_task(self, task: Task):
        """
        Update a task in the blackboard.

        Args:
            task: The task with updated fields
        """
        state = self.read()
        for i, t in enumerate(state.tasks):
            if t.id == task.id:
                state.tasks[i] = task
                break
        self.write(state)

    def transition_task(
        self,
        task_id: str,
        new_status: TaskStatus,
        agent: str | None = None,
        details: dict | None = None,
    ) -> Task:
        """
        Transition a task to a new status with history.

        Args:
            task_id: Task to transition
            new_status: Target status
            agent: Agent performing the transition
            details: Additional details for history

        Returns:
            The updated Task

        Raises:
            ValueError: If task not found
        """
        state = self.read()

        task = None
        for t in state.tasks:
            if t.id == task_id:
                task = t
                break

        if task is None:
            raise ValueError(f"Task {task_id} not found")

        old_status = task.status
        task.status = new_status
        task.add_history(
            f"status_changed",
            agent=agent,
            details={"from": old_status.value, "to": new_status.value, **(details or {})},
        )

        state.log.append(f"{task_id}: {old_status.value} -> {new_status.value}")
        self.write(state)
        return task

    def claim_task(self, task_id: str, coder: str) -> Task:
        """
        Claim a task for implementation.

        Args:
            task_id: Task to claim
            coder: Agent claiming the task

        Returns:
            The claimed Task
        """
        state = self.read()

        task = None
        for t in state.tasks:
            if t.id == task_id:
                task = t
                break

        if task is None:
            raise ValueError(f"Task {task_id} not found")

        if task.status not in (TaskStatus.UNCLAIMED, TaskStatus.REJECTED):
            raise ValueError(f"Task {task_id} cannot be claimed (status: {task.status.value})")

        task.coder = coder
        task.status = TaskStatus.CLAIMED
        task.add_history("task_claimed", agent=coder)

        if task.status == TaskStatus.REJECTED:
            task.iteration += 1

        state.log.append(f"{task_id} claimed by {coder}")
        self.write(state)
        return task

    def submit_for_review(
        self,
        task_id: str,
        implementation_summary: str | None = None,
    ) -> Task:
        """
        Submit a task for review.

        Args:
            task_id: Task to submit
            implementation_summary: Optional summary of implementation

        Returns:
            The submitted Task
        """
        state = self.read()

        task = None
        for t in state.tasks:
            if t.id == task_id:
                task = t
                break

        if task is None:
            raise ValueError(f"Task {task_id} not found")

        task.status = TaskStatus.READY_FOR_REVIEW
        task.last_implementation = implementation_summary
        task.add_history("submitted_for_review", agent=task.coder, details={
            "iteration": task.iteration,
            "summary": implementation_summary[:200] if implementation_summary else None,
        })

        state.log.append(f"{task_id} submitted for review (iteration {task.iteration})")
        self.write(state)
        return task

    def record_review(
        self,
        task_id: str,
        reviewer: str,
        verdict: str,
        feedback: str | None = None,
    ) -> Task:
        """
        Record a review verdict.

        Args:
            task_id: Task being reviewed
            reviewer: Reviewing agent
            verdict: APPROVE or REJECT
            feedback: Review feedback

        Returns:
            The reviewed Task
        """
        state = self.read()

        task = None
        for t in state.tasks:
            if t.id == task_id:
                task = t
                break

        if task is None:
            raise ValueError(f"Task {task_id} not found")

        task.add_review(reviewer, verdict, feedback)
        task.add_history("review_received", agent=reviewer, details={
            "verdict": verdict,
            "has_feedback": feedback is not None,
        })

        state.log.append(f"{task_id} reviewed by {reviewer}: {verdict}")
        self.write(state)
        return task

    def finalize_reviews(self, task_id: str) -> tuple[Task, bool]:
        """
        Finalize all reviews for a task iteration.

        Merges feedback from all reviewers and determines final verdict.
        All reviewers must APPROVE for the task to be approved.

        Args:
            task_id: Task to finalize

        Returns:
            Tuple of (updated Task, approved: bool)
        """
        state = self.read()

        task = None
        for t in state.tasks:
            if t.id == task_id:
                task = t
                break

        if task is None:
            raise ValueError(f"Task {task_id} not found")

        # Get reviews from current iteration
        current_reviews = [r for r in task.reviews if r.iteration == task.iteration]

        # Check if all reviewers approved
        all_approved = all(r.verdict == "APPROVE" for r in current_reviews)
        any_feedback = [r.feedback for r in current_reviews if r.feedback]

        if all_approved:
            task.status = TaskStatus.APPROVED
            task.add_history("all_reviews_approved", details={
                "reviewers": [r.reviewer for r in current_reviews],
            })
            state.log.append(f"{task_id} APPROVED by all reviewers")
        else:
            task.status = TaskStatus.REJECTED
            # Merge all feedback
            task.merged_feedback = "\n\n---\n\n".join(
                f"**{r.reviewer}** ({r.verdict}):\n{r.feedback or '(no feedback)'}"
                for r in current_reviews
            )
            task.add_history("reviews_require_changes", details={
                "rejecting_reviewers": [r.reviewer for r in current_reviews if r.verdict != "APPROVE"],
            })
            state.log.append(f"{task_id} REJECTED - needs iteration")

        self.write(state)
        return task, all_approved

    def get_active_tasks(self) -> list[Task]:
        """Get all non-terminal tasks."""
        state = self.read()
        terminal = {TaskStatus.APPROVED, TaskStatus.MERGED, TaskStatus.SUPERSEDED}
        return [t for t in state.tasks if t.status not in terminal]

    def log_message(self, message: str):
        """Add a message to the blackboard log."""
        state = self.read()
        state.log.append(f"[{datetime.now(timezone.utc).isoformat()}] {message}")
        self.write(state)
