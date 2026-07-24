# Copilot and Executive Decision Center Plan

**Goal:** Provide permission-aware OWL Copilot and executive decision interfaces using asynchronous AI analyses and cached summaries.

**Architecture:** Dashboard aggregation returns bounded, permission-filtered evidence. Copilot questions are persisted as conversation messages and queued as AI analyses. Executive summaries are requested explicitly, then cached after a background analysis completes; dashboard loads read cache only.

## Constraints

- No UI action invokes an LLM or operational document action directly.
- Source links and input evidence are persisted with every conversation response.
- Executive dashboard endpoints return stored/aggregated data only.
- Scenario and risk widgets degrade to empty result sets until their Phase 3 models are installed.

## Tasks

- [x] Add backend tests and observe their initial failure.
- [x] Add dashboard aggregation service.
- [x] Add AI conversations and queued Copilot request service.
- [x] Add executive cache and decision-support endpoints.
- [x] Add OWL actions, responsive templates, and QUnit registration tests.
- [x] Run isolated install and targeted tests.
