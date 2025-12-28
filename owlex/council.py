"""
Council orchestration logic for multi-agent deliberation.
Handles parallel execution and deliberation rounds.
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Any

from .config import config
from .engine import engine, build_agent_response, aider_runner, codex_runner, gemini_runner, opencode_runner
from .prompts import build_deliberation_prompt
from .models import (
    Agent,
    ClaudeOpinion,
    CouncilResponse,
    CouncilRound,
    CouncilMetadata,
)


def _log(msg: str):
    """Log progress to stderr for CLI visibility."""
    print(msg, file=sys.stderr, flush=True)


class Council:
    """
    Orchestrates multi-agent deliberation between Aider, Codex, and Gemini.

    The council process:
    1. Round 1: All agents answer the question in parallel
    2. Round 2 (optional): Agents see each other's answers and revise/critique
    """

    def __init__(self, context: Any = None, task_engine: Any = None):
        """
        Initialize the Council.

        Args:
            context: MCP server context for notifications
            task_engine: Optional TaskEngine instance (uses global engine if not provided).
                        This enables dependency injection for testing.
        """
        self.context = context
        self._engine = task_engine if task_engine is not None else engine
        self.log_entries: list[str] = []

    def log(self, msg: str):
        """Add to log and print to stderr."""
        self.log_entries.append(msg)
        _log(msg)

    async def deliberate(
        self,
        prompt: str,
        working_directory: str | None = None,
        claude_opinion: str | None = None,
        deliberate: bool = True,
        critique: bool = True,
        timeout: int | None = None,
    ) -> CouncilResponse:
        """
        Run a council deliberation session.

        Args:
            prompt: The question or task to deliberate on
            working_directory: Working directory context for agents (defaults to CWD)
            claude_opinion: Optional Claude opinion to share with agents
            deliberate: If True, run a second round where agents see each other's answers
            critique: If True, Round 2 asks agents to find flaws instead of revise
            timeout: Timeout per agent in seconds

        Returns:
            CouncilResponse with all rounds and metadata
        """
        if timeout is None:
            timeout = config.default_timeout

        # Default to CWD if no working_directory provided
        # This ensures Aider's history file persists between R1 and R2
        if working_directory is None:
            working_directory = os.getcwd()

        council_start = datetime.now()

        # === Round 1: Parallel initial queries ===
        if claude_opinion and claude_opinion.strip():
            self.log(f"Claude's opinion received ({len(claude_opinion)} chars)")

        # Determine which agents to run
        excluded = config.council.exclude_agents
        agents = [a for a in ["aider", "codex", "gemini", "opencode"] if a not in excluded]
        self.log(f"Round 1: querying {', '.join(a.title() for a in agents)}...")

        round_1 = await self._run_round_1(prompt, working_directory, timeout)

        round_2 = None
        if deliberate:
            round_2 = await self._run_round_2(
                prompt=prompt,
                working_directory=working_directory,
                round_1=round_1,
                claude_opinion=claude_opinion,
                critique=critique,
                timeout=timeout,
            )

        # Build Claude opinion object if provided
        claude_opinion_obj = None
        if claude_opinion and claude_opinion.strip():
            claude_opinion_obj = ClaudeOpinion(
                content=claude_opinion.strip(),
                provided_at=council_start.isoformat(),
            )

        return CouncilResponse(
            prompt=prompt,
            working_directory=working_directory,
            deliberation=deliberate,
            critique=critique,
            claude_opinion=claude_opinion_obj,
            round_1=round_1,
            round_2=round_2,
            metadata=CouncilMetadata(
                total_duration_seconds=(datetime.now() - council_start).total_seconds(),
                rounds=2 if deliberate else 1,
                log=self.log_entries,
            ),
        )

    async def _run_round_1(
        self,
        prompt: str,
        working_directory: str | None,
        timeout: int,
    ) -> CouncilRound:
        """Run the first round of parallel queries.

        Option A: R1 uses exec mode (clean start) for all agents.
        Session IDs are captured after completion for use in R2.
        """
        round1_start = datetime.now()
        excluded = config.council.exclude_agents

        tasks = {}
        async_tasks = []

        # Create tasks for non-excluded agents
        # All R1 agents use exec mode (clean start) per Option A
        if "aider" not in excluded:
            aider_task = self._engine.create_task(
                command=f"council_{Agent.AIDER.value}",
                args={"prompt": prompt, "working_directory": working_directory},
                context=self.context,
            )
            tasks["aider"] = aider_task

            async def run_aider():
                await self._engine.run_agent(
                    aider_task, aider_runner, mode="exec",
                    prompt=prompt, working_directory=working_directory
                )
                elapsed = (datetime.now() - round1_start).total_seconds()
                status = "completed" if aider_task.status == "completed" else "failed"
                self.log(f"Aider {status} ({elapsed:.1f}s)")

            aider_task.async_task = asyncio.create_task(run_aider())
            async_tasks.append(aider_task.async_task)

        if "codex" not in excluded:
            codex_task = self._engine.create_task(
                command=f"council_{Agent.CODEX.value}",
                args={"prompt": prompt, "working_directory": working_directory},
                context=self.context,
            )
            tasks["codex"] = codex_task

            async def run_codex():
                # Clean start for R1 - session ID captured after completion
                await self._engine.run_agent(
                    codex_task, codex_runner, mode="exec",
                    prompt=prompt, working_directory=working_directory, enable_search=config.codex.enable_search
                )
                elapsed = (datetime.now() - round1_start).total_seconds()
                status = "completed" if codex_task.status == "completed" else "failed"
                self.log(f"Codex {status} ({elapsed:.1f}s)")

            codex_task.async_task = asyncio.create_task(run_codex())
            async_tasks.append(codex_task.async_task)

        if "gemini" not in excluded:
            gemini_task = self._engine.create_task(
                command=f"council_{Agent.GEMINI.value}",
                args={"prompt": prompt, "working_directory": working_directory},
                context=self.context,
            )
            tasks["gemini"] = gemini_task

            async def run_gemini():
                # Clean start for R1 - session ID captured after completion
                await self._engine.run_agent(
                    gemini_task, gemini_runner, mode="exec",
                    prompt=prompt, working_directory=working_directory
                )
                elapsed = (datetime.now() - round1_start).total_seconds()
                status = "completed" if gemini_task.status == "completed" else "failed"
                self.log(f"Gemini {status} ({elapsed:.1f}s)")

            gemini_task.async_task = asyncio.create_task(run_gemini())
            async_tasks.append(gemini_task.async_task)

        if "opencode" not in excluded:
            opencode_task = self._engine.create_task(
                command=f"council_{Agent.OPENCODE.value}",
                args={"prompt": prompt, "working_directory": working_directory},
                context=self.context,
            )
            tasks["opencode"] = opencode_task

            async def run_opencode():
                # Clean start for R1 - session ID captured after completion
                await self._engine.run_agent(
                    opencode_task, opencode_runner, mode="exec",
                    prompt=prompt, working_directory=working_directory
                )
                elapsed = (datetime.now() - round1_start).total_seconds()
                status = "completed" if opencode_task.status == "completed" else "failed"
                self.log(f"OpenCode {status} ({elapsed:.1f}s)")

            opencode_task.async_task = asyncio.create_task(run_opencode())
            async_tasks.append(opencode_task.async_task)

        # Wait for all tasks with timeout
        if async_tasks:
            done, pending = await asyncio.wait(
                async_tasks,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED
            )

            # Kill subprocesses for any tasks that timed out
            for task in tasks.values():
                if task.async_task in pending:
                    self.log(f"{task.command} timed out")
                    await self._engine.kill_task_subprocess(task)
                    task.status = "failed"
                    task.error = f"Timed out after {timeout} seconds"
                    task.completion_time = datetime.now()

        round1_elapsed = (datetime.now() - round1_start).total_seconds()
        self.log(f"Round 1 complete ({round1_elapsed:.1f}s)")

        # Capture session IDs from completed R1 agents for R2 resume
        # Each runner parses session ID from filesystem (most reliable method)
        codex_session = codex_runner.parse_session_id("") if "codex" in tasks and tasks["codex"].status == "completed" else None
        gemini_session = gemini_runner.parse_session_id("") if "gemini" in tasks and tasks["gemini"].status == "completed" else None
        opencode_session = opencode_runner.parse_session_id("") if "opencode" in tasks and tasks["opencode"].status == "completed" else None

        return CouncilRound(
            aider=build_agent_response(tasks["aider"], Agent.AIDER) if "aider" in tasks else None,
            codex=build_agent_response(tasks["codex"], Agent.CODEX, session_id=codex_session) if "codex" in tasks else None,
            gemini=build_agent_response(tasks["gemini"], Agent.GEMINI, session_id=gemini_session) if "gemini" in tasks else None,
            opencode=build_agent_response(tasks["opencode"], Agent.OPENCODE, session_id=opencode_session) if "opencode" in tasks else None,
        )

    async def _run_round_2(
        self,
        prompt: str,
        working_directory: str | None,
        round_1: CouncilRound,
        claude_opinion: str | None,
        critique: bool,
        timeout: int,
    ) -> CouncilRound:
        """Run the second round of deliberation.

        Option A: R2 uses explicit session IDs from R1 to resume.
        Falls back to exec mode if session ID is not available.
        """
        self.log("Round 2: deliberation phase...")
        excluded = config.council.exclude_agents

        # Get explicit session IDs from R1 (Option A)
        # If session_id is None, we fall back to exec mode
        codex_session = round_1.codex.session_id if round_1.codex else None
        gemini_session = round_1.gemini.session_id if round_1.gemini else None
        opencode_session = round_1.opencode.session_id if round_1.opencode else None

        aider_content = (round_1.aider.content or round_1.aider.error or "(no response)") if round_1.aider else None
        codex_content = (round_1.codex.content or round_1.codex.error or "(no response)") if round_1.codex else None
        gemini_content = (round_1.gemini.content or round_1.gemini.error or "(no response)") if round_1.gemini else None
        opencode_content = (round_1.opencode.content or round_1.opencode.error or "(no response)") if round_1.opencode else None
        claude_content = claude_opinion.strip() if claude_opinion else None

        deliberation_prompt = build_deliberation_prompt(
            original_prompt=prompt,
            aider_answer=aider_content,
            codex_answer=codex_content,
            gemini_answer=gemini_content,
            opencode_answer=opencode_content,
            claude_answer=claude_content,
            critique=critique,
        )

        round2_start = datetime.now()
        tasks = {}
        async_tasks = []

        # R2 resumes from R1 sessions using explicit session IDs (Option A)
        # Aider: uses exec (context preserved via .aider.chat.history.md file)
        # Codex: uses resume with explicit session ID from R1
        # Gemini: uses resume with explicit session index from R1
        # OpenCode: uses resume with explicit session ID from R1
        #
        # If session ID is None (R1 failed or parsing failed), fall back to exec mode

        if "aider" not in excluded:
            aider_delib_task = self._engine.create_task(
                command=f"council_{Agent.AIDER.value}_delib",
                args={"prompt": deliberation_prompt, "working_directory": working_directory},
                context=self.context,
            )
            tasks["aider"] = aider_delib_task

            async def run_aider_delib():
                # Aider preserves context via history file - use exec mode
                await self._engine.run_agent(
                    aider_delib_task, aider_runner, mode="exec",
                    prompt=deliberation_prompt, working_directory=working_directory
                )
                elapsed = (datetime.now() - round2_start).total_seconds()
                self.log(f"Aider revised ({elapsed:.1f}s)")

            aider_delib_task.async_task = asyncio.create_task(run_aider_delib())
            async_tasks.append(aider_delib_task.async_task)

        if "codex" not in excluded:
            codex_delib_task = self._engine.create_task(
                command=f"council_{Agent.CODEX.value}_delib",
                args={"prompt": deliberation_prompt, "working_directory": working_directory},
                context=self.context,
            )
            tasks["codex"] = codex_delib_task

            # Capture session in closure
            _codex_session = codex_session

            async def run_codex_delib():
                # Resume with explicit session ID if available, otherwise exec
                if _codex_session:
                    await self._engine.run_agent(
                        codex_delib_task, codex_runner, mode="resume",
                        session_ref=_codex_session,
                        prompt=deliberation_prompt, working_directory=working_directory,
                        enable_search=config.codex.enable_search
                    )
                else:
                    await self._engine.run_agent(
                        codex_delib_task, codex_runner, mode="exec",
                        prompt=deliberation_prompt, working_directory=working_directory,
                        enable_search=config.codex.enable_search
                    )
                elapsed = (datetime.now() - round2_start).total_seconds()
                self.log(f"Codex revised ({elapsed:.1f}s)")

            codex_delib_task.async_task = asyncio.create_task(run_codex_delib())
            async_tasks.append(codex_delib_task.async_task)

        if "gemini" not in excluded:
            gemini_delib_task = self._engine.create_task(
                command=f"council_{Agent.GEMINI.value}_delib",
                args={"prompt": deliberation_prompt, "working_directory": working_directory},
                context=self.context,
            )
            tasks["gemini"] = gemini_delib_task

            # Capture session in closure
            _gemini_session = gemini_session

            async def run_gemini_delib():
                # Resume with explicit session index if available, otherwise exec
                if _gemini_session:
                    await self._engine.run_agent(
                        gemini_delib_task, gemini_runner, mode="resume",
                        session_ref=_gemini_session,
                        prompt=deliberation_prompt, working_directory=working_directory
                    )
                else:
                    await self._engine.run_agent(
                        gemini_delib_task, gemini_runner, mode="exec",
                        prompt=deliberation_prompt, working_directory=working_directory
                    )
                elapsed = (datetime.now() - round2_start).total_seconds()
                self.log(f"Gemini revised ({elapsed:.1f}s)")

            gemini_delib_task.async_task = asyncio.create_task(run_gemini_delib())
            async_tasks.append(gemini_delib_task.async_task)

        if "opencode" not in excluded:
            opencode_delib_task = self._engine.create_task(
                command=f"council_{Agent.OPENCODE.value}_delib",
                args={"prompt": deliberation_prompt, "working_directory": working_directory},
                context=self.context,
            )
            tasks["opencode"] = opencode_delib_task

            # Capture session in closure
            _opencode_session = opencode_session

            async def run_opencode_delib():
                # Resume with explicit session ID if available, otherwise exec
                if _opencode_session:
                    await self._engine.run_agent(
                        opencode_delib_task, opencode_runner, mode="resume",
                        session_ref=_opencode_session,
                        prompt=deliberation_prompt, working_directory=working_directory
                    )
                else:
                    await self._engine.run_agent(
                        opencode_delib_task, opencode_runner, mode="exec",
                        prompt=deliberation_prompt, working_directory=working_directory
                    )
                elapsed = (datetime.now() - round2_start).total_seconds()
                self.log(f"OpenCode revised ({elapsed:.1f}s)")

            opencode_delib_task.async_task = asyncio.create_task(run_opencode_delib())
            async_tasks.append(opencode_delib_task.async_task)

        # Wait for all tasks with timeout
        if async_tasks:
            done, pending = await asyncio.wait(
                async_tasks,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED
            )

            # Kill subprocesses for any tasks that timed out
            for task in tasks.values():
                if task.async_task in pending:
                    self.log(f"{task.command} timed out")
                    await self._engine.kill_task_subprocess(task)
                    task.status = "failed"
                    task.error = f"Timed out after {timeout} seconds"
                    task.completion_time = datetime.now()

        round2_elapsed = (datetime.now() - round2_start).total_seconds()
        self.log(f"Round 2 complete ({round2_elapsed:.1f}s)")

        return CouncilRound(
            aider=build_agent_response(tasks["aider"], Agent.AIDER) if "aider" in tasks else None,
            codex=build_agent_response(tasks["codex"], Agent.CODEX) if "codex" in tasks else None,
            gemini=build_agent_response(tasks["gemini"], Agent.GEMINI) if "gemini" in tasks else None,
            opencode=build_agent_response(tasks["opencode"], Agent.OPENCODE) if "opencode" in tasks else None,
        )
