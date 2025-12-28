"""
Tests for session management logic.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from owlex.agents.codex import CodexRunner, get_latest_codex_session
from owlex.agents.gemini import GeminiRunner, get_gemini_session_for_project, _get_gemini_project_hash
from owlex.agents.opencode import OpenCodeRunner, get_latest_opencode_session, _get_opencode_project_id
from owlex.agents.base import AgentRunner


class TestSessionIdValidation:
    """Tests for session ID validation in base runner."""

    def setup_method(self):
        self.codex = CodexRunner()
        self.gemini = GeminiRunner()
        self.opencode = OpenCodeRunner()

    def test_rejects_empty_session_id(self):
        assert not self.codex.validate_session_id("")
        assert not self.gemini.validate_session_id("")
        assert not self.opencode.validate_session_id("")

    def test_rejects_flag_injection(self):
        """Session IDs starting with dash could be interpreted as CLI flags."""
        assert not self.codex.validate_session_id("--help")
        assert not self.codex.validate_session_id("-v")
        assert not self.gemini.validate_session_id("--version")
        assert not self.opencode.validate_session_id("-n")

    def test_rejects_shell_metacharacters(self):
        """Session IDs with shell metacharacters could enable command injection."""
        dangerous_chars = [";", "|", "&", "$", "`", "(", ")", "{", "}", "<", ">", "\n", "\r"]
        for char in dangerous_chars:
            bad_id = f"session{char}evil"
            assert not self.codex.validate_session_id(bad_id), f"Should reject '{char}'"
            assert not self.opencode.validate_session_id(bad_id), f"Should reject '{char}'"

    def test_accepts_valid_uuid_style_session(self):
        """Valid UUID-style session IDs should be accepted."""
        valid_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert self.codex.validate_session_id(valid_uuid)
        assert self.opencode.validate_session_id(valid_uuid)

    def test_accepts_valid_opencode_session_id(self):
        """OpenCode uses ses_XXX format."""
        valid_id = "ses_49b5d1b81ffeZfa2uTg3NVmKrH"
        assert self.opencode.validate_session_id(valid_id)


class TestGeminiSessionValidation:
    """Tests for Gemini-specific session validation."""

    def setup_method(self):
        self.gemini = GeminiRunner()

    def test_accepts_numeric_index(self):
        """Gemini uses 1-indexed numeric indices for -r flag."""
        assert self.gemini.validate_session_id("1")
        assert self.gemini.validate_session_id("5")
        assert self.gemini.validate_session_id("100")

    def test_rejects_zero_index(self):
        """Gemini uses 1-indexed sessions, so 0 is invalid."""
        assert not self.gemini.validate_session_id("0")

    def test_accepts_latest_keyword(self):
        """Gemini accepts 'latest' as a session reference."""
        assert self.gemini.validate_session_id("latest")

    def test_rejects_non_numeric(self):
        """Gemini only accepts numeric indices or 'latest'."""
        assert not self.gemini.validate_session_id("abc")
        assert not self.gemini.validate_session_id("session-1")

    def test_rejects_flag_injection(self):
        """Even Gemini-specific validation rejects flags."""
        assert not self.gemini.validate_session_id("--help")
        assert not self.gemini.validate_session_id("-v")


class TestProjectHashComputation:
    """Tests for project hash computation matching CLI behavior."""

    def test_gemini_hash_uses_abspath(self):
        """Gemini hash should use os.path.abspath, not resolve()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = os.path.join(tmpdir, "project")
            os.makedirs(test_path)

            # Verify hash is computed from abspath
            expected_path = os.path.abspath(test_path)
            import hashlib
            expected_hash = hashlib.sha256(expected_path.encode()).hexdigest()

            assert _get_gemini_project_hash(test_path) == expected_hash

    def test_opencode_project_id_lookup(self):
        """OpenCode projectID should be looked up from config files, not computed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = os.path.join(tmpdir, "project")
            os.makedirs(test_path)

            # Create a mock project config file
            project_dir = Path(tmpdir) / ".local" / "share" / "opencode" / "storage" / "project"
            project_dir.mkdir(parents=True)
            import json
            project_id = "mock_project_id_12345"
            project_file = project_dir / f"{project_id}.json"
            with open(project_file, "w") as f:
                json.dump({"id": project_id, "worktree": os.path.abspath(test_path)}, f)

            # Lookup should find the project
            with patch.object(Path, 'home', return_value=Path(tmpdir)):
                result = _get_opencode_project_id(test_path)
                assert result == project_id

    def test_opencode_project_id_returns_none_for_unknown(self):
        """OpenCode projectID lookup should return None for unknown projects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # No project config files exist
            project_dir = Path(tmpdir) / ".local" / "share" / "opencode" / "storage" / "project"
            project_dir.mkdir(parents=True)

            with patch.object(Path, 'home', return_value=Path(tmpdir)):
                result = _get_opencode_project_id("/some/unknown/path")
                assert result is None

    def test_relative_path_produces_consistent_hash(self):
        """Relative and absolute paths to same dir should produce same hash."""
        cwd = os.getcwd()
        # Use absolute and relative paths
        abs_hash = _get_gemini_project_hash(cwd)
        rel_hash = _get_gemini_project_hash(".")

        assert abs_hash == rel_hash


class TestAsyncSessionParsing:
    """Tests for async session parsing methods."""

    @pytest.mark.asyncio
    async def test_codex_parse_session_id_is_async(self):
        """Codex parse_session_id should be awaitable (coroutine)."""
        runner = CodexRunner()
        # Verify it's a coroutine function
        import inspect
        assert inspect.iscoroutinefunction(runner.parse_session_id)
        # Should be awaitable without raising
        result = await runner.parse_session_id("")
        # Result can be None or a session ID depending on system state
        assert result is None or isinstance(result, str)

    @pytest.mark.asyncio
    async def test_gemini_parse_session_id_is_async(self):
        """Gemini parse_session_id should be awaitable (coroutine)."""
        runner = GeminiRunner()
        import inspect
        assert inspect.iscoroutinefunction(runner.parse_session_id)
        result = await runner.parse_session_id("")
        # Result can be None or "1" depending on system state
        assert result is None or result == "1"

    @pytest.mark.asyncio
    async def test_opencode_parse_session_id_is_async(self):
        """OpenCode parse_session_id should be awaitable (coroutine)."""
        runner = OpenCodeRunner()
        import inspect
        assert inspect.iscoroutinefunction(runner.parse_session_id)
        result = await runner.parse_session_id("")
        # Result can be None or a session ID depending on system state
        assert result is None or isinstance(result, str)

    @pytest.mark.asyncio
    async def test_base_parse_session_id_is_async(self):
        """Base AgentRunner parse_session_id should be awaitable."""
        # Create a concrete subclass for testing
        class TestRunner(AgentRunner):
            @property
            def name(self):
                return "test"

            def build_exec_command(self, prompt, **kwargs):
                pass

            def build_resume_command(self, session_ref, prompt, **kwargs):
                pass

            def get_output_cleaner(self):
                return lambda x, y: x

        runner = TestRunner()
        import inspect
        assert inspect.iscoroutinefunction(runner.parse_session_id)
        result = await runner.parse_session_id("")
        assert result is None  # Base class returns None


class TestCodexSessionDiscovery:
    """Tests for Codex session file discovery."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_sessions_dir(self):
        """Should return None when ~/.codex/sessions doesn't exist."""
        with patch.object(Path, 'exists', return_value=False):
            result = await get_latest_codex_session()
            assert result is None

    @pytest.mark.asyncio
    async def test_respects_since_mtime_filter(self):
        """Should ignore sessions older than since_mtime."""
        import time
        # Create a fake session directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock the codex sessions path
            codex_dir = Path(tmpdir) / ".codex" / "sessions"
            from datetime import datetime
            now = datetime.now()
            date_dir = codex_dir / f"{now.year}" / f"{now.month:02d}" / f"{now.day:02d}"
            date_dir.mkdir(parents=True)

            # Create an old session file
            session_file = date_dir / "rollout-2025-01-01T12-00-00-abc123def456.jsonl"
            session_file.touch()

            # Set mtime to the past
            old_mtime = time.time() - 3600  # 1 hour ago
            os.utime(session_file, (old_mtime, old_mtime))

            # Search with since_mtime in the future
            with patch.object(Path, 'home', return_value=Path(tmpdir)):
                result = await get_latest_codex_session(since_mtime=time.time())
                assert result is None  # Should be filtered out


class TestGeminiSessionDiscovery:
    """Tests for Gemini session discovery."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_gemini_dir(self):
        """Should return False when ~/.gemini/tmp doesn't exist."""
        with patch.object(Path, 'exists', return_value=False):
            result = await get_gemini_session_for_project("/some/path")
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_working_directory(self):
        """Should return False when working_directory is None to prevent cross-project contamination."""
        result = await get_gemini_session_for_project(working_directory=None)
        assert result is False

    @pytest.mark.asyncio
    async def test_scoped_by_project_hash(self):
        """Session search should be scoped to the project's hash directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gemini_dir = Path(tmpdir) / ".gemini" / "tmp"
            project_hash = _get_gemini_project_hash("/test/project")
            project_dir = gemini_dir / project_hash / "chats"
            project_dir.mkdir(parents=True)

            # Create a session file
            session_file = project_dir / "session-abc123.json"
            session_file.touch()

            with patch.object(Path, 'home', return_value=Path(tmpdir)):
                # Should find session for correct project
                result = await get_gemini_session_for_project("/test/project")
                assert result is True

                # Should not find session for different project
                result = await get_gemini_session_for_project("/other/project")
                assert result is False


class TestOpenCodeSessionDiscovery:
    """Tests for OpenCode session discovery."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_opencode_dir(self):
        """Should return None when storage dir doesn't exist."""
        with patch.object(Path, 'exists', return_value=False):
            result = await get_latest_opencode_session(working_directory="/some/path")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_working_directory(self):
        """Should return None when working_directory is None to prevent cross-project contamination."""
        result = await get_latest_opencode_session(working_directory=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_extracts_session_id_from_filename(self):
        """Should extract session ID from ses_*.json filename."""
        import json as json_module
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project config file (required for lookup)
            project_config_dir = Path(tmpdir) / ".local" / "share" / "opencode" / "storage" / "project"
            project_config_dir.mkdir(parents=True)
            project_id = "test_project_abc123"
            project_file = project_config_dir / f"{project_id}.json"
            with open(project_file, "w") as f:
                json_module.dump({"id": project_id, "worktree": "/test/project"}, f)

            # Create session directory and file
            opencode_dir = Path(tmpdir) / ".local" / "share" / "opencode" / "storage" / "session"
            project_dir = opencode_dir / project_id
            project_dir.mkdir(parents=True)

            # Create a session file
            session_file = project_dir / "ses_abc123xyz.json"
            session_file.touch()

            with patch.object(Path, 'home', return_value=Path(tmpdir)):
                result = await get_latest_opencode_session(working_directory="/test/project")
                assert result == "ses_abc123xyz"


class TestServerValidation:
    """Tests for session validation in server API endpoints."""

    def test_codex_runner_validates_session_ref(self):
        """Codex runner should validate session IDs before use."""
        runner = CodexRunner()

        # Valid sessions should pass
        assert runner.validate_session_id("abc123def456")

        # Invalid sessions should fail
        assert not runner.validate_session_id("--help")
        assert not runner.validate_session_id("id;rm -rf /")

    def test_gemini_runner_validates_session_ref(self):
        """Gemini runner should validate session references."""
        runner = GeminiRunner()

        # Valid references
        assert runner.validate_session_id("1")
        assert runner.validate_session_id("latest")

        # Invalid references
        assert not runner.validate_session_id("--help")
        assert not runner.validate_session_id("abc")
