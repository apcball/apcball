# S&OP Production Capacity Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stored, calendar-aware work-center capacity demand, availability, utilization, status, and recommendations to S&OP production plans.

**Architecture:** Capacity rows aggregate each calculated production line's active BOM operations by work center and required period. Planned duration is deterministic from operation cycle minutes, setup/cleanup minutes, product quantity, and work-center parallel capacity. Availability is resource-calendar work intervals multiplied by work-center capacity; overlapping standard work-center productivity-loss intervals are deducted as maintenance downtime.

**Tech Stack:** Odoo 17 ORM, `mrp.bom`, `mrp.routing.workcenter`, `mrp.workcenter`, resource calendars, Odoo TransactionCase.

## Global Constraints

- Target Odoo 17 and Python 3.10+.
- Modify only `mogen_sop_production`; do not modify Odoo core.
- Store planning results and use batch source queries.
- Respect company and warehouse isolation.
- Do not create or confirm MOs, POs, transfers, or sequencing documents.
- Do not implement production sequencing optimization.

---

### Task 1: Add Failing Capacity Tests

**Files:**
- Modify: `mogen_sop_production/tests/test_production_plan.py`

**Interfaces:**
- Consumes: calculated production lines with BOM operations.
- Produces: test contracts for `action_calculate_capacity()` and `capacity_line_ids`.

- [ ] **Step 1: Write tests before production code**

```python
production_plan.action_calculate_production()
production_plan.action_calculate_capacity()
capacity = production_plan.capacity_line_ids
self.assertEqual(capacity.planned_hours, 3.0)
self.assertEqual(capacity.effective_available_hours, 8.0)
self.assertEqual(capacity.capacity_load_percent, 37.5)
```

Cover cycle/setup/cleanup and parallel capacity, calendar absence, productivity-loss downtime, zero effective capacity, warning/overload status, aggregation, and company isolation.

- [ ] **Step 2: Run focused Odoo tests and confirm failures**

Run: isolated Odoo update with `--test-tags /mogen_sop_production`.

Expected: tests fail because the action and relation do not exist.

### Task 2: Implement Stored Capacity Calculations

**Files:**
- Modify: `mogen_sop_production/models/production_plan.py`

**Interfaces:**
- Consumes: `mrp.routing.workcenter.time_cycle`, `mrp.workcenter.time_start`, `time_stop`, `default_capacity`, resource calendar intervals, and productivity losses.
- Produces: `mogen.sop.workcenter.capacity` and `action_calculate_capacity()`.

- [ ] **Step 1: Add fields and model**

```python
capacity_line_ids = fields.One2many(
    "mogen.sop.workcenter.capacity", "production_plan_id", readonly=True
)

capacity_load_percent = fields.Float(required=True, readonly=True)
status = fields.Selection([...], required=True, readonly=True)
```

- [ ] **Step 2: Batch BOM operations and planned hours**

```python
cycles = math.ceil(line.planned_production_qty / workcenter.default_capacity)
planned_hours += (
    operation.time_cycle * cycles + workcenter.time_start + workcenter.time_stop
) / 60.0
```

Read operations once for all selected BOMs, apply Odoo's operation variant predicate, and aggregate by work center and period.

- [ ] **Step 3: Calendar and maintenance availability**

```python
effective_available_hours = max(0.0, available_hours - maintenance_hours)
load = planned_hours / effective_available_hours * 100 if effective_available_hours else 0.0
```

Use `_work_intervals_batch()` for one work-center resource at a time and overlap productivity-loss intervals against the period. A zero effective capacity with planned work is `overloaded`; a zero effective capacity without planned work is `available`.

- [ ] **Step 4: Thresholds, recommendations, and idempotence**

Store warning and overload thresholds on the production plan, defaulted to 85 and 100. Recalculate stored rows by `(workcenter, period)`, replacing stale rows. Create a readable recommendation only on the capacity row; do not generate documents or change planning state.

### Task 3: Add Security and Capacity Views

**Files:**
- Modify: `mogen_sop_production/security/ir.model.access.csv`
- Modify: `mogen_sop_production/security/production_security.xml`
- Modify: `mogen_sop_production/views/production_plan_views.xml`

**Interfaces:**
- Consumes: stored capacity rows.
- Produces: company rule, form smart button, tabular capacity page, capacity pivot and graph views.

- [ ] **Step 1: Add read-only ACL and company record rule**

```xml
<field name="domain_force">[('company_id', 'in', company_ids)]</field>
```

- [ ] **Step 2: Add capacity actions and analytic views**

```xml
<graph type="bar"><field name="workcenter_id"/><field name="planned_hours" type="measure"/></graph>
<pivot><field name="workcenter_id" type="row"/><field name="period_date" type="col"/></pivot>
```

### Task 4: Verify and Review

**Files:**
- Verify: `mogen_sop_production/`

- [ ] **Step 1: Compile Python and validate XML**

Run: `python3 -m compileall -q mogen_sop_production` and XML parsing.

- [ ] **Step 2: Run isolated focused Odoo tests**

Run: `odoo ... -u mogen_sop_production --test-enable --test-tags /mogen_sop_production --stop-after-init --no-http`.

- [ ] **Step 3: Request and incorporate code review**

Review all Step 5 requirements and resolve blockers before handoff.
