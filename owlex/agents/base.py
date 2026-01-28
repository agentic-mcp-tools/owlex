"""
Base agent runner interface.
Defines the contract that all agent runners must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable


@dataclass
class AgentCommand:
    """Command specification for running an agent."""
    command: list[str]
    prompt: str
    cwd: str | None = None
    output_prefix: str = "Output"
    not_found_hint: str | None = None
    stream: bool = True
    env_overrides: dict[str, str] | None = None  # Environment variable overrides


class AgentRunner(ABC):
    """
    Abstract base class for agent runners.
    Each agent implementation knows how to build its CLI commands.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the agent."""
        pass

    @abstractmethod
    def build_exec_command(
        self,
        prompt: str,
        working_directory: str | None = None,
        enable_search: bool = False,
        **kwargs,
    ) -> AgentCommand:
        """Build command for starting a new session."""
        pass

    @abstractmethod
    def build_resume_command(
        self,
        session_ref: str,
        prompt: str,
        working_directory: str | None = None,
        enable_search: bool = False,
        **kwargs,
    ) -> AgentCommand:
        """Build command for resuming an existing session."""
        pass

    @abstractmethod
    def get_output_cleaner(self) -> Callable[[str, str], str]:
        """Return the output cleaning function for this agent."""
        pass

    async def parse_session_id(
        self,
        output: str,
        since_mtime: float | None = None,
        working_directory: str | None = None,
    ) -> str | None:
        """
        Parse session ID from agent's output or filesystem.

        Override in subclasses to extract session IDs from CLI output or filesystem.
        Returns None if no session ID found (will trigger fallback to exec mode).

        This method is async to allow non-blocking retries with asyncio.sleep().

        Args:
            output: The agent's stdout/stderr output
            since_mtime: Only consider sessions created after this timestamp.
                        Used to scope to sessions from the current run.
            working_directory: Working directory context to scope session discovery.

        Returns:
            Session ID string if found, None otherwise
        """
        return None

    def validate_session_id(self, session_id: str) -> bool:
        """
        Validate a session ID before use in resume commands.

        Checks for potential flag injection or malformed IDs.

        Args:
            session_id: The session ID to validate

        Returns:
            True if valid, False otherwise
        """
        if not session_id:
            return False
        # Reject IDs that start with dash (flag injection)
        if session_id.startswith("-"):
            return False
        # Reject IDs with shell metacharacters
        if any(c in session_id for c in [";", "|", "&", "$", "`", "(", ")", "{", "}", "<", ">", "\n", "\r"]):
            return False
        return True
