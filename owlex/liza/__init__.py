"""
Liza - Peer-supervised multi-agent coding system for owlex.

Implements the Liza protocol: disciplined peer-supervised coding where
agents take coder/reviewer roles with binding verdicts.

Based on: https://github.com/liza-mas/liza
"""

from .blackboard import Blackboard, Task, TaskStatus, AgentRole
from .protocol import ReviewVerdict, VerdictStatus, parse_verdict
from .contracts import CoderContract, ReviewerContract, get_contract_prompt
from .orchestrator import LizaOrchestrator, LizaConfig, LizaResult

__all__ = [
    # Blackboard
    "Blackboard",
    "Task",
    "TaskStatus",
    "AgentRole",
    # Protocol
    "ReviewVerdict",
    "VerdictStatus",
    "parse_verdict",
    # Contracts
    "CoderContract",
    "ReviewerContract",
    "get_contract_prompt",
    # Orchestrator
    "LizaOrchestrator",
    "LizaConfig",
    "LizaResult",
]
