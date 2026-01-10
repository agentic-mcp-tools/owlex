---
name: council
description: Consult the AI council (Codex + Gemini + OpenCode) for multi-perspective answers
user-invocable: true
allowed-tools:
  - mcp__owlex__council_ask
---

# Council Deliberation

Start an owlex council deliberation - queries Codex, Gemini, and OpenCode in parallel with 2-round deliberation.

## Instructions

1. Take the user's question or task from: $ARGUMENTS
2. If no argument provided, ask what they want the council to discuss
3. Call `mcp__owlex__council_ask` with:
   - `prompt`: The user's question/task
   - `working_directory`: Current working directory
   - `deliberate`: true
   - `critique`: false
4. Return immediately with the task_id
5. Tell the user:
   - "Council started (task: <task_id>)"
   - "This typically takes 2-5 minutes"
   - "Check results with: `/council-result <task_id>`"
   - "Or check status with: `/council-status`"

**Do NOT call wait_for_task. Return immediately after council_ask.**

## Usage

- `/council How should I structure this auth system?`
- `/council Review this code for bugs`
