# AI Gateway and Structured Recommendation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Add auditable, background AI gateway analyses and strictly validated draft S&OP recommendations.

**Architecture:** Business models queue analyses only. A cron job invokes a dedicated gateway client with a bounded timeout and retry policy. A validation service parses structured JSON, validates accessible Odoo references and safe values, and creates AI recommendation records; only an AI manager can convert an approved record to a draft core S&OP recommendation.

**Tech Stack:** Odoo 17 ORM, `requests`, Python 3.10+, PostgreSQL.

## Global Constraints

- Provider records store configuration references only; API keys resolve from an environment variable or an `ir.config_parameter` key at execution time.
- No compute method, normal request, or AI output may confirm or post operational or accounting documents.
- Gateway calls occur only in scheduled background processing.
- Output actions are restricted to the seven documented S&OP draft recommendation actions.

## Tasks

- [x] Add mocked gateway/validation tests and observe their initial failure.
- [x] Add secure provider and prompt-template models.
- [x] Add queued analysis processing, timeout, and retry handling.
- [x] Add structured JSON and record-access validation.
- [x] Add approval-gated conversion to core draft recommendations.
- [x] Add security, scheduled processing, views, and documentation.
- [x] Run isolated Odoo installation and targeted tests.
