# Mogen Smart S&OP Core

Foundation module for Mogen's Odoo 17 Smart Sales and Operations Planning
application.

## Included

- Multi-company planning cycles with monthly or weekly granularity
- Controlled workflow from draft through data preparation, review, consensus,
  approval, and lock
- Sequential, immutable plan versions with a single current version
- Base, optimistic, pessimistic, and custom planning scenarios
- Auditable recommendations and alerts
- Viewer, demand planner, supply planner, manager, and administrator roles
- Company record rules and read-only approved-plan access for viewers
- Standard list, form, search, pivot, and graph views

The plan form exposes integration points for demand lines, supply lines, and
inventory health. Those calculations and the creation of purchase or
manufacturing orders are intentionally implemented by later Smart S&OP
modules, not by this core module.

## Workflow

`Draft → Data Prepared → Review → Consensus → Approved → Locked`

Managers approve plans and recommendations. Locked plans and their versions
can only be changed or reset by an S&OP administrator.

## Demo data

With demo data enabled, the module creates base, optimistic, and pessimistic
scenarios plus one annual planning cycle.

Shared Smart S&OP menu structure and security roles. Phase 1 model workflow is introduced in Step 2.
