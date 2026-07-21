# Mogen Landed Cost MO Filter View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Manufacturing Order Filter on the standard manufacturing landed-cost form so its inputs and action remain readable at normal desktop widths.

**Architecture:** Keep the existing model fields and search action unchanged. Make the filter group span both columns of the surrounding standard form while retaining Odoo's four-cell grid (two label/widget field pairs per row), then place the selection mode and action in a final row.

**Tech Stack:** Odoo 17 XML view inheritance; existing Odoo TransactionCase test suite.

## Global Constraints

- Modify only the `mogen_landed_cost_mo_filter` addon for the requested redesign.
- Preserve the existing `stock.landed.cost` fields and `action_search_manufacturing_orders` behaviour.
- Display the filter only for draft manufacturing landed costs.
- Follow Odoo 17 XML syntax and standard CSS classes.

---

### Task 1: Assert the responsive filter view structure

**Files:**
- Modify: `mogen_landed_cost_mo_filter/tests/test_landed_cost_mo_filter.py`

**Interfaces:**
- Consumes: `stock.landed.cost` form view provided by `mrp_landed_costs.view_mrp_landed_costs_form`.
- Produces: A regression test proving the inherited view loads and exposes the intended full-width filter layout.

- [ ] **Step 1: Write the failing test**

```python
def test_filter_view_uses_a_full_width_two_field_layout(self):
    view = self.env.ref(
        'mogen_landed_cost_mo_filter.view_mrp_landed_costs_form_inherit_mo_filter'
    )
    arch = view.arch_db
    self.assertIn('class="o_mo_filter"', arch)
    self.assertIn('col="4"', arch)
    self.assertIn('class="o_mo_filter_actions"', arch)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose -f docker-compose.test.yml up --abort-on-container-exit`

Expected: FAIL because the XML view does not yet contain `o_mo_filter` or `o_mo_filter_actions` classes.

- [ ] **Step 3: Write the minimal view redesign**

```xml
<group string="Manufacturing Order Filter" class="o_mo_filter" col="4" colspan="2"
       invisible="state != 'draft' or target_model != 'manufacturing'">
    <field name="mo_filter_analytic_account_id"/>
    <field name="mo_filter_state"/>
    <field name="mo_filter_date_from"/>
    <field name="mo_filter_date_to"/>
    <field name="mo_filter_mode" colspan="2"/>
    <div class="o_mo_filter_actions" colspan="2">
        <button name="action_search_manufacturing_orders" type="object"
                string="Search Manufacturing Orders" icon="fa-search"
                class="btn-primary"/>
    </div>
</group>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker compose -f docker-compose.test.yml up --abort-on-container-exit`

Expected: exit code 0 with the view loading and the addon tests passing.

- [ ] **Step 5: Inspect the upgrade result**

Run: `docker compose -f docker-compose.test.yml up --abort-on-container-exit`

Expected: Odoo upgrades `mogen_landed_cost_mo_filter` without an XML validation error.
