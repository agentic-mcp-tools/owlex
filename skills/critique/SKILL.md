---
name: critique
description: Council critique mode - agents find bugs and flaws in each other's answers
user-invocable: true
allowed-tools:
  - mcp__owlex__council_ask
---

# Council Critique Mode

Start an owlex council in **critique mode** - agents actively find bugs, security issues, and flaws.

## Instructions

1. Take the user's question or code from: $ARGUMENTS
2. If no argument provided, ask what they want critiqued
3. Call `mcp__owlex__council_ask` with:
   - `prompt`: The user's question/code to critique
   - `working_directory`: Current working directory
   - `deliberate`: true
   - `critique`: true (enables adversarial mode)
4. Return immediately with the task_id
5. Tell the user:
   - "Critique started (task: <task_id>)"
   - "This typically takes 2-5 minutes"
   - "Check results with: `/council-result <task_id>`"

**Do NOT call wait_for_task. Return immediately.**

## Usage

- `/critique Review this auth for security holes`
- `/critique Find bugs in this payment code`
