# Sale Forecast Module - Comprehensive Test Plan

## Module Overview
- **Module:** sale_forecast (v17.0.2.0.0)
- **Purpose:** Forecast sales demand, auto-allocate to orders, track forecast accuracy
- **Key Features:** Forecast planning, auto-allocation on SO confirm, OWL dashboard

---

## Test File Structure

```
tests/
├── __init__.py
├── common.py              # Test helpers, fixtures, common setup
├── test_forecast_plan.py  # Unit tests for forecast.plan model
├── test_forecast_line.py  # Unit tests for forecast.line model
├── test_forecast_allocation.py # Unit tests for forecast.allocation model
├── test_auto_allocation.py     # Integration tests for SO confirm auto-allocation
└── test_security.py      # Security tests for 3 user groups
```

---

## 1. Test File: `test_forecast_plan.py`

### 1.1 Plan Creation Tests
- ✅ Create draft plan with default values (user = current user, start_date = first of month)
- ✅ Create plan with specific user and month
- ✅ Verify sequence generates unique plan reference
- ✅ Verify end_date computed as start_date + 3 months - 1 day

### 1.2 SQL Constraint Tests
- ❌ **CRITICAL:** Create 2 plans for same user + same month + same company → should fail with ValidationError
- ✅ Create 2 plans for same user + different months → should pass
- ✅ Create 2 plans for different users + same month → should pass

### 1.3 Validation Tests
- ❌ Create plan with start_date != first of month → should fail with ValidationError
- ✅ Create plan with valid start_date (first of month) → should pass

### 1.4 State Workflow Tests
- ✅ Draft → Confirmed → Done (happy path)
- ✅ Draft → Cancelled
- ✅ Done → Cancelled → Set to Draft
- ✅ Confirmed → Cancelled → Set to Draft
- ✅ Verify tracking fields work with chatter

### 1.5 Computed Fields Tests
- ✅ Add forecast lines → verify total_forecast_qty computed
- ✅ Create allocations → verify total_allocated_qty computed
- ✅ Mark allocations/sales as delivered → verify total_actual_sold_qty computed
- ✅ Verify allocation_rate = (allocated / forecast * 100)
- ✅ Verify accuracy_rate = (actual / forecast * 100)
- ✅ Zero forecast → allocation_rate = 0, accuracy_rate = 0 (no division by zero)

### 1.6 Weekly Distribution Tests
- ✅ Plan with lines → action_distribute_weekly() → all lines distributed evenly
- ✅ Verify action_view_lines_analysis() returns correct action

---

## 2. Test File: `test_forecast_line.py`

### 2.1 Line Creation Tests
- ✅ Create forecast line with product, qty, arrival_month, expected_week
- ✅ Verify default week = "1"
- ✅ Verify product_uom_id derived from product_id

### 2.2 Validation Tests
- ❌ Create line with forecast_qty <= 0 → should fail
- ✅ Create line with forecast_qty > 0 → should pass
- ❌ Create line with arrival_month < current month → should fail
- ❌ Create line with arrival_month > current month + 2 months → should fail
- ✅ Create line with arrival_month = current month → should pass
- ✅ Create line with arrival_month = current month + 1 → should pass
- ✅ Create line with arrival_month = current month + 2 → should pass

### 2.3 Weekly Distribution Tests
- ✅ Create line → verify auto-applies even distribution on create
- ✅ Create line with 4-week month (28 days) → distributed across W1-W4 only
- ✅ Create line with 5-week month (29-31 days) → distributed across W1-W5
- ✅ Verify rounding: total weekly qty = forecast_qty (within 0.01 tolerance)
- ❌ Manually set week1_qty+week2_qty+... != forecast_qty → should fail constraint
- ✅ Trigger _onchange_distribute_weeks → verify re-distribution
- ✅ Update forecast_qty → verify weeks re-distributed
- ✅ action_distribute_evenly() → manual trigger works

### 2.4 KPI Computed Fields Tests
- ✅ Create line with forecast_qty = 100 → verify remaining_qty = 100
- ✅ Create allocation (not non-forecast) → verify allocated_qty increases, remaining_qty decreases
- ✅ Create non-forecast allocation → verify allocated_qty unchanged (only non-forecast doesn't count)
- ✅ Mark sale as delivered → verify actual_sold_qty increases
- ✅ Verify allocation_rate = (allocated / forecast * 100)
- ✅ Verify accuracy_rate = (actual / forecast * 100)

### 2.5 Edge Cases
- ✅ Zero forecast_qty → allocation_rate = 0, accuracy_rate = 0
- ✅ Cancel allocation → verify it doesn't affect allocated_qty
- ✅ Multiple allocations to same line → verify all summed correctly

---

## 3. Test File: `test_forecast_allocation.py`

### 3.1 Allocation Creation Tests
- ✅ Create allocation with plan_id, plan_line_id, product_id, allocated_qty, sale_order_id
- ✅ Verify sequence generates unique allocation reference
- ✅ Verify default state = "confirmed"
- ✅ Create with plan_line_id but no product_id → auto-populate product_id
- ✅ Create without plan_line_id → is_non_forecast = False by default
- ✅ Verify related fields: customer_id, salesperson_id, order_date, company_id, month

### 3.2 Onchange Tests
- ✅ Change plan_line_id → product_id auto-updates
- ✅ Verify onchange doesn't trigger on create (Odoo behavior)

### 3.3 Validation Tests
- ❌ Create allocation with plan_line_id from different plan → should fail
- ❌ Create allocation where plan_line_id.product_id != product_id → should fail
- ❌ Create allocation with allocated_qty <= 0 → should fail

### 3.4 Over-Allocation Prevention Tests (CRITICAL)
- ✅ Create line with forecast_qty = 100 → allocation 100 → should pass
- ❌ Create line with forecast_qty = 100 → allocation 100 → allocation 1 more → should fail
- ✅ Create line with forecast_qty = 100 → allocation 50 → allocation 50 → should pass
- ❌ Create line with forecast_qty = 100 → allocation 51 → allocation 50 → should fail
- ✅ Cancel first allocation → can now allocate 100 again
- ✅ Non-forecast allocation (is_non_forecast=True) → should NOT count against forecast_qty

### 3.5 Actual Sold Qty Computation Tests
- ✅ Allocation in state "cancel" → actual_sold_qty = 0
- ✅ Allocation in confirmed state, sale order in "draft" → actual_sold_qty = 0
- ✅ Allocation confirmed, sale order in "sale", qty_delivered = 10 → actual_sold_qty = 10
- ✅ Allocation confirmed, sale order in "sale", qty_delivered = None, product_uom_qty = 10 → actual_sold_qty = 10
- ✅ Allocation confirmed, sale order in "done" → actual_sold_qty uses delivered qty

### 3.6 Sale Order Line Integration Tests
- ✅ Create allocation → verify sale_order_line_id auto-created
- ✅ Verify sale_order_line_id.forecast_allocation_id = allocation.id
- ✅ Verify sale_order_line_id.is_forecast_allocation = True if is_non_forecast=False
- ✅ Verify sale_order_line_id.is_non_forecast = is_non_forecast value
- ✅ Update allocation qty → sale_order_line_id.product_uom_qty updated
- ✅ Cancel allocation → no change to sale_order_line_id

### 3.7 State Workflow Tests
- ✅ Create with state="confirmed" → action_cancel → state="cancel"
- ✅ Create with state="draft" → action_confirm → state="confirmed"

---

## 4. Test File: `test_auto_allocation.py` (INTEGRATION)

### 4.1 Auto-Allocation Trigger Tests
- ✅ Create forecast plan for user A in current month
- ✅ Create SO for user A → Confirm → verify allocations created automatically
- ✅ SO in "draft" state → confirm → allocations created
- ✅ SO in "sent" state → confirm → allocations created
- ❌ SO without user_id → confirm → no allocations created
- ❌ SO without user_id + no plan exists → confirm → no allocations created

### 4.2 Product Matching Tests
- ✅ Forecast line with Product X (100 qty) → SO line with Product X (50 qty) → confirm → allocation 50 created
- ✅ Forecast line with Product X (100 qty) → SO line with Product X (150 qty) → confirm → allocation 100 + non-forecast 50
- ❌ SO line with Product Y (not in forecast) → confirm → non-forecast allocation created

### 4.3 Partial Allocation Tests
- ✅ Forecast line with Product X (100 qty) → SO1 line Product X (60) + SO2 line Product X (30) → both confirm → allocations 60 and 30 created
- ✅ Forecast line with Product X (100 qty) → SO line Product X (150) → confirm → allocation 100 + non-forecast allocation 50

### 4.4 Multi-Line SO Tests
- ✅ SO with 3 lines: Product X (10), Product Y (20), Product Z (30) → all in forecast → confirm → 3 allocations created
- ✅ SO with mixed lines: X in forecast, Y not in forecast → confirm → allocation for X, non-forecast for Y

### 4.5 Non-Forecast Product Tests
- ✅ SO line with product not in forecast → confirm → is_non_forecast=True allocation created
- ✅ Verify SO line.is_non_forecast = True
- ✅ Verify SO line.is_forecast_allocation = False

### 4.6 Duplicate Allocation Prevention Tests
- ✅ Create SO, confirm → allocations created
- ✅ Confirm again → should NOT create duplicate allocations
- ✅ Update SO line qty → confirm again → should NOT create new allocations (existing remain)

### 4.7 Multiple Forecast Lines Same Product Tests
- ✅ 2 forecast lines for Product X: W1 (50 qty), W2 (50 qty) → SO line Product X (30) → confirm → allocation from W1 (or W2)
- ✅ 2 forecast lines for Product X: W1 (50 qty), W2 (50 qty) → SO line Product X (120) → confirm → allocation 100 + non-forecast 20

### 4.8 Arrival Month Filtering Tests
- ✅ Forecast line for Product X in January → SO confirmed in January → allocation created
- ❌ Forecast line for Product X in January → SO confirmed in February → no allocation (month mismatch)
- ✅ 2 forecast lines for Product X: January (100), February (200) → SO confirmed in January → allocation from January line only

### 4.9 Sale Order Smart Button Tests
- ✅ SO with allocations → forecast_allocation_count computed correctly
- ✅ action_view_forecast_allocations() → returns action with correct domain

---

## 5. Test File: `test_security.py`

### 5.1 Forecast Planner Role Tests
- ✅ Can read/write/create/unlink forecast.plan
- ✅ Can read/write/create/unlink forecast.line
- ✅ Can ONLY read forecast.allocation (no write/create/unlink)
- ❌ Planner tries to create allocation → should fail (no permission)

### 5.2 Forecast Sales Allocator Role Tests
- ✅ Can read/write/create forecast.plan (no unlink)
- ✅ Can ONLY read forecast.line (no write/create/unlink)
- ✅ Can read forecast.allocation (no write/create/unlink)
- ❌ Sales allocator tries to unlink plan → should fail
- ❌ Sales allocator tries to write line → should fail

### 5.3 Forecast Manager Role Tests
- ✅ Can read/write/create/unlink forecast.plan
- ✅ Can read/write/create/unlink forecast.line
- ✅ Can read/write/create/unlink forecast.allocation
- ✅ Manager can modify all records created by planner/sales

### 5.4 Cross-Role Access Tests
- ✅ Planner creates plan → Manager can see and modify
- ✅ Planner creates plan → Sales Allocator can see but not delete
- ✅ Manager creates allocation → Planner can read but not modify

### 5.5 Record Rules Tests (if any defined)
- **Note:** Review security XML for additional record rules beyond access.csv

---

## 6. Test File: `common.py`

### Common Fixtures/Helpers

```python
class ForecastTestCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create users with different roles
        cls.user_planner = cls.env["res.users"].create({...})
        cls.user_sales = cls.env["res.users"].create({...})
        cls.user_manager = cls.env["res.users"].create({...})

        # Create products
        cls.product_a = cls.env["product.product"].create({...})
        cls.product_b = cls.env["product.product"].create({...})

        # Create partner (customer)
        cls.partner = cls.env["res.partner"].create({...})
```

Helper methods:
- `create_forecast_plan(user, month_start)` - Returns plan
- `create_forecast_line(plan, product, qty)` - Returns line
- `create_allocation(plan, line, qty, sale_order)` - Returns allocation
- `create_sale_order(user, lines)` - Returns SO
- `confirm_sale_order(so)` - Triggers auto-allocation

---

## 7. Edge Cases & Additional Tests

### 7.1 Concurrency Tests (if applicable)
- ✅ Multiple users confirming SOs simultaneously → verify no over-allocation

### 7.2 Data Integrity Tests
- ✅ Delete plan → verify cascade delete to lines works
- ✅ Delete plan → verify allocations remain (no cascade)
- ✅ Delete line → verify allocations with plan_line_id set to null

### 7.3 Dashboard Tests (Optional - if needed)
- ✅ Dashboard KPIs compute correctly
- ✅ Dashboard filters by user/month work

### 7.4 Translation Tests
- ✅ Verify all ValidationError messages are translatable (_() wrapper)

### 7.5 Currency Tests (if multi-currency)
- ✅ Verify prices work correctly in different currencies

---

## 8. Test Coverage Goals

| Model | Target Coverage | Priority |
|-------|----------------|----------|
| forecast.plan | 90% | HIGH |
| forecast.line | 90% | HIGH |
| forecast.allocation | 90% | HIGH |
| sale.order (auto-allocation) | 85% | HIGH |
| Security | 80% | MEDIUM |
| Dashboard | 50% | LOW (manual testing OK) |

**Overall Module Coverage Target:** 85%

---

## 9. Test Execution Order

1. Run `test_forecast_plan.py` (foundational model)
2. Run `test_forecast_line.py` (depends on plan)
3. Run `test_forecast_allocation.py` (depends on line)
4. Run `test_auto_allocation.py` (integration, depends on all above)
5. Run `test_security.py` (can run in parallel with others)

---

## 10. Known Constraints & Assumptions

- Forecast horizon: current month + next 2 months only
- 1 plan per user per month per company (SQL constraint)
- Weekly distribution auto-applies on create (can be manually overridden)
- Auto-allocation only triggers on SO confirm, not on create
- Non-forecast products are allowed (flagged but not blocked)
- Dashboard is JavaScript-based (manual testing recommended for UI)

---

## 11. Mock Data Requirements

- 3 test users (planner, sales, manager)
- 3-5 products (sale_ok=True)
- 1 customer partner
- Test company (or use default company)
- Sequences: forecast.plan, forecast.allocation

---

## 12. Dependencies & Setup

Required Odoo modules to install before testing:
- sale_management
- mail
- sales_team (for sale manager group)

---

## Test Plan Summary

| Test File | Test Classes | Estimated Test Methods | Priority |
|-----------|--------------|------------------------|----------|
| test_forecast_plan.py | 3-4 | 25-30 | HIGH |
| test_forecast_line.py | 3-4 | 20-25 | HIGH |
| test_forecast_allocation.py | 4-5 | 30-35 | HIGH |
| test_auto_allocation.py | 3-4 | 25-30 | HIGH |
| test_security.py | 3-4 | 20-25 | MEDIUM |
| common.py | 1 | (helper only) | - |

**Total Estimated Test Methods:** ~120-145

---

*Test Plan Created: 2025-01-XX*
*Reviewer: Tester (QA)*
*Status: Ready for Implementation*
