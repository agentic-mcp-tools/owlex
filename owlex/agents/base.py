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

    def parse_session_id(self, output: str) -> str | None:
        """
        Parse session ID from agent's output.

        Override in subclasses to extract session IDs from CLI output.
        Returns None if no session ID found (will trigger fallback to exec mode).

        Args:
            output: The agent's stdout/stderr output

        Returns:
            Session ID string if found, None otherwise
        """
        return None
