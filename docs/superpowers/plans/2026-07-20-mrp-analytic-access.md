# MO Analytic Distribution Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a dedicated user group to see and edit `Analytic Distribution` on Manufacturing Orders without granting Inventory Administrator.

**Architecture:** Create a standalone custom addon `buz_mrp_analytic_access`. Define a dedicated security group and inherit the standard `mrp_account.mrp_production_form_view_inherited` view, widening only the wrapper around the existing MO analytic field from `stock.group_stock_manager` to the dedicated group. Keep the standard Inventory Administrator access unchanged.

**Tech Stack:** Odoo 17 addon, XML security groups, inherited XML view, Odoo module update on DEV.

## Global Constraints

- Use Odoo 17 XML and module conventions.
- Do not edit standard Odoo files or unrelated existing working-tree changes.
- The dedicated group must also require `analytic.group_analytic_accounting` because the field itself has that group restriction.
- Test on DEV before any PROD deployment.

---

### Task 1: Add the addon scaffold and security group

**Files:**
- Create: `buz_mrp_analytic_access/__init__.py`
- Create: `buz_mrp_analytic_access/__manifest__.py`
- Create: `buz_mrp_analytic_access/security/security.xml`

- [ ] Create a minimal addon manifest with dependencies `mrp_account` and `analytic`, and load `security/security.xml`.
- [ ] Define `group_mrp_analytic_distribution_user` with label `MO Analytic Distribution` in the Inventory category and imply `analytic.group_analytic_accounting`.
- [ ] Verify the new files parse as valid Python/XML before adding the view.

### Task 2: Add the inherited MO form view

**Files:**
- Create: `buz_mrp_analytic_access/views/mrp_production_views.xml`

- [ ] Inherit `mrp_account.mrp_production_form_view_inherited`.
- [ ] Locate only the miscellaneous-tab wrapper containing `analytic_distribution`.
- [ ] Change that wrapper's groups to `stock.group_stock_manager,buz_mrp_analytic_access.group_mrp_analytic_distribution_user`.
- [ ] Keep the field's existing `analytic.group_analytic_accounting` restriction and widget/options unchanged.

### Task 3: Add a regression test and run the red-green cycle

**Files:**
- Create: `buz_mrp_analytic_access/tests/__init__.py`
- Create: `buz_mrp_analytic_access/tests/test_mrp_analytic_access.py`

- [ ] Add an Odoo `TransactionCase` that asserts the dedicated group implies `analytic.group_analytic_accounting` and that the inherited view contains the dedicated group on the analytic field wrapper.
- [ ] Run the test before implementation and confirm the expected missing-module/view failure.
- [ ] Install/update the addon on the isolated DEV Odoo database and run the test again.

### Task 4: Verify DEV behavior

- [ ] Update `buz_mrp_analytic_access` on DEV with the repository deployment command.
- [ ] Confirm the module is installed and the inherited view is active.
- [ ] Test with a DEV user having Analytic Accounting plus the new group, but not Inventory Administrator.
- [ ] Test with a DEV user having only Analytic Accounting and confirm the field remains hidden.
- [ ] Confirm `git status` shows only the new addon and this plan.
