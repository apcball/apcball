# Project Instructions

This file provides context for AI assistants working on this project.

## Project Type: Unknown

<!-- Add build/test commands here -->

### Version Control
This project uses Git. See .gitignore for excluded files.

## Agent Guidance

<!-- How should an AI agent approach this project? Fill in tool gotchas, -->
<!-- file patterns to avoid, and anything that helps a model navigate -->
<!-- the codebase without reading every file. -->

- **CodeWhale reads this file as:** <!-- WHALE.md (CodeWhale-native) or AGENTS.md (compatible with other agents) -->
- **Read-only surface:** <!-- Which directories can the agent read but not write? -->
- **Never edit:** <!-- Files that are generated, vendored, or owned by another tool -->
- **Always test with:** <!-- The single command that validates a change (e.g. `cargo test -p foo`) -->

## Architecture

<!-- Describe the high-level structure. What are the key modules and how -->
<!-- do they connect? Focus on the context a new contributor would need. -->

### Entry Points
<!-- Where does execution start? Binary entry, request handler, main loop? -->

### Key Modules
<!-- List the 3-6 most important directories/files and their role -->

### Data Flow
<!-- How does a request / event / input travel through the system? -->

## Cache Stability

<!-- DeepSeek V4 uses a byte-stable prefix cache (128-token granularity). -->
<!-- Keeping these things stable turn-over-turn saves ~90% on input tokens. -->

- **Frequently-rebuilt files:** <!-- Generated code, lockfiles, build artifacts → mark as cache-churn -->
- **Stable scaffolding:** <!-- Config files, project instructions, model cards → keep byte-stable -->
- **Append, don't reorder:** <!-- New context goes at the end of the request; reordering invalidates cache -->

## Guidelines

- Follow existing code style and patterns
- Write tests for new functionality
- Keep changes focused and atomic
- Document public APIs
- Update this file when project conventions change
