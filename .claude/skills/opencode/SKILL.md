---
name: opencode-agent
description: Invokes OpenCode (autonomous AI agent) for independent task execution. Use when task requires full agent autonomy, deep codebase exploration, or parallel work streams that don't fit Claude Code's single-session model.
metadata:
  type: skill
---

# OpenCode Agent Skill

## What It Does

Spawns OpenCode (open-source AI agent, MIT licensed) as an autonomous worker alongside Claude Code. OpenCode runs independently with its own terminal UI / desktop app and can:

- Execute full development tasks without human-in-loop
- Explore large codebases in read-only mode (plan agent)
- Handle long-running operations while Claude Code handles other work
- Switch agents via Tab key (@general, @build, @plan subagents)

## When to Use

- **Claude Code**: Single session, context-rich, tight feedback loops, design decisions, code review
- **OpenCode**: Autonomous execution, fire-and-forget exploration, parallel work, large refactors where you want independent verification

**Don't use OpenCode for:** security-critical code (no guardrails in autonomous mode), immediate decisions, or tasks needing your project context loaded.

## How to Invoke

```bash
# Install (one-liner)
curl -fsSL https://opencode.ai/install | bash

# Run
opencode
```

Then switch agents in the TUI using Tab.

## Delegation Pattern

1. **Claude Code** designs the task, writes specification
2. **OpenCode** executes autonomously (build agent)
3. **Claude Code** reviews the result, integrates it

**Example (good):**
```
claude:   "Refactor auth middleware into 3 modules per spec in REFACTOR.md"
opencode: [runs 2h autonomously, pushes branch]
claude:   [reviews PR, merges]
```

**Example (bad):**
```
claude: "Run opencode to fix this bug"
        ↳ No spec → OpenCode guesses → wrong fix
```

## See Also

- CLAUDE.md (task delegation section)
- opencode.ai/docs (official configuration)

---

**Version:** 1.0.0  
**Created:** 2026-07-16
