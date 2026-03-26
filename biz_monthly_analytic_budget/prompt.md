# prompt.md — Hardening Monthly Analytic Budget Engine (v2)

## 🎯 Objective

Enhance `biz_monthly_analytic_budget` to be **production-safe, concurrency-safe, and data-consistent** by implementing:

1. Concurrency / Race Condition Protection
2. Robust Analytic Distribution Parsing
3. Reserved vs Used Consistency Mechanism
4. SQL View Performance Optimization

All implementations must be:

* Atomic
* Idempotent (where applicable)
* Multi-company safe
* Compatible with Odoo ORM + PostgreSQL

---

# 1️⃣ Concurrency / Race Condition Protection

## Problem

Multiple PR/PO confirmations can update the same `monthly.budget.line` simultaneously, causing **overspending**.

## Solution Strategy

Use **row-level locking (PostgreSQL `FOR UPDATE`)** to ensure atomic updates.

## Implementation

### A. Add Locking Method

```python
def _lock_budget_lines(self, analytic_account_ids, plan_id):
    query = """
        SELECT id FROM monthly_budget_line
        WHERE analytic_account_id IN %s
        AND plan_id = %s
        FOR UPDATE
    """
    self.env.cr.execute(query, (tuple(analytic_account_ids), plan_id))
```

---

### B. Apply Lock in Critical Sections

#### PR → Reservation

```python
def _reserve_monthly_analytic_budget(self):
    plan = self._get_budget_plan()

    analytic_ids = self._extract_analytic_ids()

    self._lock_budget_lines(analytic_ids, plan.id)

    # re-read AFTER lock
    budget_lines = self._get_budget_lines(plan, analytic_ids)

    self._check_monthly_analytic_budget(budget_lines)

    self._apply_reservation(budget_lines)
```

---

#### PO → Consumption

```python
def _consume_monthly_analytic_budget(self):
    plan = self._get_budget_plan()

    analytic_ids = self._extract_analytic_ids()

    self._lock_budget_lines(analytic_ids, plan.id)

    budget_lines = self._get_budget_lines(plan, analytic_ids)

    self._apply_consumption(budget_lines)
```

---

## Requirements

* MUST re-read data after acquiring lock
* MUST wrap in single transaction
* NEVER compute before locking

---

# 2️⃣ Analytic Distribution Parsing

## Problem

`analytic_distribution` JSON:

* May not sum to 100
* Float precision issues
* Missing/invalid keys

---

## Solution Strategy

* Normalize distribution
* Use `Decimal`
* Validate strictly

---

## Implementation

### A. Utility Method

```python
from decimal import Decimal, ROUND_HALF_UP

def _normalize_distribution(self, distribution):
    total = sum(Decimal(str(v)) for v in distribution.values())

    if total == 0:
        raise UserError("Analytic distribution total cannot be zero")

    normalized = {}
    for acc_id, value in distribution.items():
        pct = (Decimal(str(value)) / total) * Decimal('100')
        normalized[acc_id] = pct.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    return normalized
```

---

### B. Convert to Amount

```python
def _compute_distribution_amount(self, total_amount, distribution):
    normalized = self._normalize_distribution(distribution)

    result = {}
    for acc_id, pct in normalized.items():
        amount = (Decimal(str(total_amount)) * pct / Decimal('100'))
        result[acc_id] = amount.quantize(Decimal('0.0001'))

    return result
```

---

## Requirements

* Precision: 4 decimal places
* Reject invalid distributions
* Always normalize before use

---

# 3️⃣ Reserved vs Used Consistency

## Problem

Possible inconsistencies:

* PR cancelled but reservation not released
* PO cancelled but used not reverted
* Partial flows

---

## Solution Strategy

Introduce **single source of truth recomputation**

---

## Implementation

### A. Central Recompute Method

```python
def _recompute_line_balance(self):
    for line in self:
        reserved = self._compute_reserved_from_source(line)
        used = self._compute_used_from_source(line)

        line.write({
            'reserved_amount': reserved,
            'used_amount': used,
        })
```

---

### B. Source Computation

```python
def _compute_reserved_from_source(self, line):
    commitments = self.env['budget.commitment'].search([
        ('analytic_account_id', '=', line.analytic_account_id.id),
        ('state', '=', 'reserved'),
        ('plan_id', '=', line.plan_id.id),
    ])
    return sum(commitments.mapped('amount'))
```

```python
def _compute_used_from_source(self, line):
    commitments = self.env['budget.commitment'].search([
        ('analytic_account_id', '=', line.analytic_account_id.id),
        ('state', '=', 'used'),
        ('plan_id', '=', line.plan_id.id),
    ])
    return sum(commitments.mapped('amount'))
```

---

### C. Add Action + Cron

#### Manual Action

```python
def action_recompute_budget(self):
    self.budget_line_ids._recompute_line_balance()
```

#### Scheduled Job

* Run daily or hourly
* Ensure system self-heals

---

## Requirements

* Budget line values MUST be derived, not trusted
* Must support manual + automatic recompute

---

# 4️⃣ SQL View Performance Optimization

## Problem

`monthly_budget_report` joins:

* budget lines
* purchase order lines

→ slow on large datasets

---

## Solution Strategy

### Option A (Recommended): Materialized View

---

### A. Create Materialized View

```sql
CREATE MATERIALIZED VIEW monthly_budget_report_mv AS
SELECT ...
```

---

### B. Add Indexes

```sql
CREATE INDEX idx_mbr_analytic ON monthly_budget_report_mv (analytic_account_id);
CREATE INDEX idx_mbr_date ON monthly_budget_report_mv (date);
CREATE INDEX idx_mbr_plan ON monthly_budget_report_mv (plan_id);
```

---

### C. Refresh Method

```python
def refresh_materialized_view(self):
    self.env.cr.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY monthly_budget_report_mv")
```

---

### D. Hook into Odoo

* Call refresh on:

  * PO confirm
  * PR confirm
  * Budget update

---

## Option B: ORM Optimization (if not using MV)

* Add indexes on:

  * purchase_order_line(analytic_distribution)
  * monthly_budget_line(analytic_account_id)

* Reduce JOIN depth

* Use aggregated pre-compute fields

---

## Requirements

* Dashboard response < 300ms (target)
* Must scale to 100k+ PO lines
* Prefer MV if dataset is large

---

# ✅ Acceptance Criteria

* No double-spend under concurrent PR/PO
* Analytic distribution always normalized
* Budget always consistent after recompute
* Dashboard performance stable under load

---

# 🚀 Bonus (Optional but Recommended)

* Add retry mechanism on lock contention
* Add audit log for every budget mutation
* Add monitoring (log slow queries)

---

# 📌 Notes for AI / Dev

* Do NOT trust computed fields without lock
* Always recompute after acquiring lock
* Treat budget as financial data → must be exact
* Prefer correctness over performance (then optimize)

---
