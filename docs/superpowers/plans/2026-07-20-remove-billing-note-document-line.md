# Remove Billing Note Document Line Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to remove an invoice/document row from a draft billing note while keeping confirmed and later states read-only.

**Architecture:** Keep the existing `billing.note.invoice_ids` Many2many relationship and expose its standard row-delete control explicitly in the Documents subview. The existing `readonly="state != 'draft'"` rule remains the state guard; no new model or database field is needed.

**Tech Stack:** Odoo 17 XML views, Odoo TransactionCase tests.

## Global Constraints

- Use Odoo 17 view syntax.
- Use the existing `buz_custom_billing_note` module structure.
- Do not delete the related `account.move` record when removing a billing-note document.
- Do not permit document removal from confirmed, done, or cancelled billing notes.

---

### Task 1: Add a failing regression test

**Files:**
- Modify: `buz_custom_billing_note/tests/test_billing_note.py`

- [ ] Add a test that loads `view_billing_note_form`, finds the Documents tree for `invoice_ids`, and asserts its `delete` attribute is enabled. Before the XML change this must fail because the attribute is absent.

```python
    def test_documents_tree_allows_removing_rows(self):
        view = self.env.ref('buz_custom_billing_note.view_billing_note_form')
        arch = view.with_context(lang='en_US').arch_db
        self.assertIn('<field name="invoice_ids"', arch)
        self.assertIn('<tree delete="1">', arch)
```

- [ ] Run the focused module test and verify it fails for the missing view attribute.

```bash
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

### Task 2: Enable document-row removal

**Files:**
- Modify: `buz_custom_billing_note/views/billing_note_views.xml`

- [x] Add `delete="1"` to the nested Documents tree under `invoice_ids`, leaving the field’s existing `readonly="state != 'draft'"` guard unchanged.

```xml
<tree delete="1">
```

- [ ] Run the focused module test again and verify it passes once Docker/OrbStack is available.

### Task 3: Verify behavior and regressions

**Files:**
- No additional files.

- [ ] Confirm the relationship operation removes only the link and preserves the invoice record using the existing billing note test setup.
- [ ] Run the module’s Odoo test suite through the isolated Docker test environment.
- [x] Inspect `git diff` and confirm only the intended test and view changes are present.
