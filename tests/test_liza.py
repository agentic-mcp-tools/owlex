"""
Tests for the Liza peer-supervised coding module.
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from owlex.liza import (
    Blackboard,
    Task,
    TaskStatus,
    LizaOrchestrator,
    LizaConfig,
    parse_verdict,
    VerdictStatus,
    ReviewVerdict,
)


class TestVerdictParsing:
    """Tests for verdict parsing from reviewer responses."""

    def test_parse_approve_xml(self):
        """Parse APPROVE verdict with XML tags."""
        response = """
        I've reviewed the implementation.

        <verdict>APPROVE</verdict>

        <feedback>
        Code looks good. Well structured and follows best practices.
        </feedback>
        """
        verdict = parse_verdict(response)
        assert verdict.status == VerdictStatus.APPROVE
        assert verdict.approved
        assert verdict.confidence >= 0.9

    def test_parse_reject_xml(self):
        """Parse REJECT verdict with XML tags."""
        response = """
        <verdict>REJECT</verdict>

        <feedback>
        Found several issues:
        - Missing input validation
        - No error handling for edge cases
        - Tests don't cover failure scenarios
        </feedback>
        """
        verdict = parse_verdict(response)
        assert verdict.status == VerdictStatus.REJECT
        assert not verdict.approved
        assert "Missing input validation" in verdict.feedback
        assert len(verdict.issues) >= 2

    def test_parse_approve_markdown(self):
        """Parse APPROVE verdict with markdown format."""
        response = """
        ## Verdict: APPROVE

        The implementation meets requirements.
        """
        verdict = parse_verdict(response)
        assert verdict.status == VerdictStatus.APPROVE

    def test_parse_reject_implicit(self):
        """Parse REJECT verdict from implicit signals."""
        response = """
        There are several problems with this implementation:
        - Missing validation
        - Bugs in error handling
        Please fix these issues before approval.
        """
        verdict = parse_verdict(response)
        assert verdict.status == VerdictStatus.REJECT
        assert verdict.confidence < 1.0  # Lower confidence than explicit XML

    def test_parse_approve_implicit(self):
        """Parse APPROVE verdict from implicit signals."""
        response = """
        Looks good to me! LGTM.
        No issues found, ready to merge.
        """
        verdict = parse_verdict(response)
        assert verdict.status == VerdictStatus.APPROVE

    def test_extract_issues(self):
        """Extract individual issues from feedback."""
        response = """
        <verdict>REJECT</verdict>
        <feedback>
        Issues found:
        - SQL injection vulnerability in login handler
        - Missing rate limiting
        - No input sanitization
        </feedback>
        """
        verdict = parse_verdict(response)
        assert len(verdict.issues) == 3
        assert any("SQL injection" in issue for issue in verdict.issues)


class TestBlackboard:
    """Tests for blackboard state management."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for blackboard."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_initialize_blackboard(self, temp_dir):
        """Initialize a new blackboard."""
        bb = Blackboard(working_directory=temp_dir)
        state = bb.initialize(goal="Test goal")

        assert state.goal == "Test goal"
        assert bb.exists()
        assert (Path(temp_dir) / ".owlex" / "liza-state.yaml").exists()

    def test_add_task(self, temp_dir):
        """Add a task to the blackboard."""
        bb = Blackboard(working_directory=temp_dir)
        bb.initialize(goal="Test goal")

        task = bb.add_task(
            description="Implement login",
            coder="claude",
            reviewers=["codex", "gemini"],
        )

        assert task.id == "task-1"
        assert task.description == "Implement login"
        assert task.coder == "claude"
        assert task.reviewers == ["codex", "gemini"]
        assert task.status == TaskStatus.UNCLAIMED

    def test_claim_task(self, temp_dir):
        """Claim a task for implementation."""
        bb = Blackboard(working_directory=temp_dir)
        bb.initialize(goal="Test goal")
        bb.add_task(description="Test task", status=TaskStatus.UNCLAIMED)

        task = bb.claim_task("task-1", "claude")

        assert task.status == TaskStatus.CLAIMED
        assert task.coder == "claude"
        assert len(task.history) >= 2  # created + claimed

    def test_submit_for_review(self, temp_dir):
        """Submit task for review."""
        bb = Blackboard(working_directory=temp_dir)
        bb.initialize(goal="Test goal")
        bb.add_task(description="Test task", coder="claude", status=TaskStatus.WORKING)

        task = bb.submit_for_review("task-1", "Implementation summary")

        assert task.status == TaskStatus.READY_FOR_REVIEW
        assert task.last_implementation == "Implementation summary"

    def test_record_review(self, temp_dir):
        """Record a review verdict."""
        bb = Blackboard(working_directory=temp_dir)
        bb.initialize(goal="Test goal")
        bb.add_task(description="Test task", reviewers=["codex"], status=TaskStatus.IN_REVIEW)

        task = bb.record_review("task-1", "codex", "APPROVE", "Looks good")

        assert len(task.reviews) == 1
        assert task.reviews[0].reviewer == "codex"
        assert task.reviews[0].verdict == "APPROVE"

    def test_finalize_reviews_approved(self, temp_dir):
        """Finalize reviews when all approve."""
        bb = Blackboard(working_directory=temp_dir)
        bb.initialize(goal="Test goal")
        bb.add_task(description="Test task", reviewers=["codex", "gemini"], status=TaskStatus.IN_REVIEW)

        bb.record_review("task-1", "codex", "APPROVE", "Good")
        bb.record_review("task-1", "gemini", "APPROVE", "LGTM")

        task, approved = bb.finalize_reviews("task-1")

        assert approved
        assert task.status == TaskStatus.APPROVED

    def test_finalize_reviews_rejected(self, temp_dir):
        """Finalize reviews when any reject."""
        bb = Blackboard(working_directory=temp_dir)
        bb.initialize(goal="Test goal")
        bb.add_task(description="Test task", reviewers=["codex", "gemini"], status=TaskStatus.IN_REVIEW)

        bb.record_review("task-1", "codex", "APPROVE", "Good")
        bb.record_review("task-1", "gemini", "REJECT", "Missing tests")

        task, approved = bb.finalize_reviews("task-1")

        assert not approved
        assert task.status == TaskStatus.REJECTED
        assert "gemini" in task.merged_feedback
        assert "Missing tests" in task.merged_feedback


class TestLizaOrchestrator:
    """Tests for the Liza orchestrator."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_create_task(self, temp_dir):
        """Create a task via orchestrator."""
        config = LizaConfig(working_directory=temp_dir)
        orchestrator = LizaOrchestrator(config=config)

        task = orchestrator.create_task(
            description="Implement feature X",
            reviewers=["codex", "gemini"],
        )

        assert task.id == "task-1"
        assert task.coder == "claude"
        assert task.status == TaskStatus.WORKING

    def test_get_task_status(self, temp_dir):
        """Get task status."""
        config = LizaConfig(working_directory=temp_dir)
        orchestrator = LizaOrchestrator(config=config)
        orchestrator.create_task(description="Test task")

        status = orchestrator.get_task_status("task-1")

        assert status is not None
        assert status["task_id"] == "task-1"
        assert status["status"] == "WORKING"

    @pytest.mark.asyncio
    async def test_submit_for_review_mock(self, temp_dir):
        """Test submitting for review with mock reviewers."""
        config = LizaConfig(
            working_directory=temp_dir,
            reviewers=["mock_reviewer"],
        )
        orchestrator = LizaOrchestrator(config=config)

        # Mock reviewer that always approves
        async def mock_runner(agent: str, prompt: str, wd: str | None, timeout: int) -> str:
            return "<verdict>APPROVE</verdict><feedback>Looks good!</feedback>"

        orchestrator.set_reviewer_runner(mock_runner)

        task = orchestrator.create_task(description="Test task", reviewers=["mock_reviewer"])
        result = await orchestrator.submit_for_review(task.id, "Implementation done")

        assert result.all_approved
        assert "mock_reviewer" in result.reviews
        assert result.reviews["mock_reviewer"].approved

    @pytest.mark.asyncio
    async def test_submit_for_review_rejected(self, temp_dir):
        """Test submitting for review with rejection."""
        config = LizaConfig(
            working_directory=temp_dir,
            reviewers=["reviewer1", "reviewer2"],
        )
        orchestrator = LizaOrchestrator(config=config)

        # Mock: one approves, one rejects
        async def mock_runner(agent: str, prompt: str, wd: str | None, timeout: int) -> str:
            if agent == "reviewer1":
                return "<verdict>APPROVE</verdict>"
            else:
                return "<verdict>REJECT</verdict><feedback>Missing validation</feedback>"

        orchestrator.set_reviewer_runner(mock_runner)

        task = orchestrator.create_task(description="Test task", reviewers=["reviewer1", "reviewer2"])
        result = await orchestrator.submit_for_review(task.id, "Implementation done")

        assert not result.all_approved
        assert result.reviews["reviewer1"].approved
        assert not result.reviews["reviewer2"].approved
        assert "Missing validation" in result.merged_feedback


class TestIntegration:
    """Integration tests for the full Liza workflow."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.mark.asyncio
    async def test_full_workflow_approved_first_try(self, temp_dir):
        """Test full workflow: create → implement → review → approved."""
        config = LizaConfig(
            working_directory=temp_dir,
            reviewers=["codex", "gemini"],
        )
        orchestrator = LizaOrchestrator(config=config)

        # All reviewers approve
        async def mock_runner(agent: str, prompt: str, wd: str | None, timeout: int) -> str:
            return f"<verdict>APPROVE</verdict><feedback>{agent} approves this implementation.</feedback>"

        orchestrator.set_reviewer_runner(mock_runner)

        # Step 1: Create task
        task = orchestrator.create_task(
            description="Add login endpoint",
            reviewers=["codex", "gemini"],
        )
        assert task.status == TaskStatus.WORKING

        # Step 2: Submit for review
        result = await orchestrator.submit_for_review(
            task.id,
            "Implemented login endpoint with validation"
        )

        # Step 3: Check result
        assert result.all_approved

        # Step 4: Verify final state
        final_task = orchestrator.blackboard.get_task(task.id)
        assert final_task.status == TaskStatus.APPROVED

    @pytest.mark.asyncio
    async def test_full_workflow_with_iteration(self, temp_dir):
        """Test full workflow with one rejection then approval."""
        config = LizaConfig(
            working_directory=temp_dir,
            reviewers=["codex"],
        )
        orchestrator = LizaOrchestrator(config=config)

        call_count = 0

        # First call rejects, second call approves
        async def mock_runner(agent: str, prompt: str, wd: str | None, timeout: int) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "<verdict>REJECT</verdict><feedback>Missing error handling</feedback>"
            else:
                return "<verdict>APPROVE</verdict><feedback>Error handling looks good now.</feedback>"

        orchestrator.set_reviewer_runner(mock_runner)

        # Create and submit
        task = orchestrator.create_task(description="Add feature", reviewers=["codex"])

        # First submission - rejected
        result1 = await orchestrator.submit_for_review(task.id, "First implementation")
        assert not result1.all_approved
        assert "Missing error handling" in result1.merged_feedback

        # Prepare for iteration
        orchestrator.prepare_for_iteration(task.id, result1.merged_feedback)
        task = orchestrator.blackboard.get_task(task.id)
        assert task.iteration == 1

        # Second submission - approved
        result2 = await orchestrator.submit_for_review(task.id, "Fixed error handling")
        assert result2.all_approved
