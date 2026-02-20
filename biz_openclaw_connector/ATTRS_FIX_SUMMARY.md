# Odoo 17 attrs Fix Summary

## Issue
The module failed to install with error:
```
ParseError: Since 17.0, "attrs" and "states" attributes are no longer used.
View: openclaw.job.form in biz_openclaw_connector/views/openclaw_job_views.xml
```

## Root Cause
Odoo 17 deprecated the `attrs` attribute. The new syntax uses direct attributes like `invisible` instead.

### Old Syntax (Deprecated):
```xml
<button attrs="{'invisible': [('state', '!=', 'error')]}"/>
<page attrs="{'invisible': [('error_message', '=', False)]}">
```

### New Syntax (Odoo 17):
```xml
<button invisible="state != 'error'"/>
<page invisible="not error_message">
```

## Changes Made

### 1. openclaw_job_views.xml
Fixed 4 instances of `attrs`:

**Header Buttons:**
- `action_retry`: `attrs="{'invisible': [('state', '!=', 'error')]}"` → `invisible="state != 'error'"`
- `action_mark_done`: `attrs="{'invisible': [('state', 'in', ['done', 'error'])}"` → `invisible="state in ['done', 'error']"`
- `action_mark_error`: `attrs="{'invisible': [('state', 'in', ['done', 'error'])}"` → `invisible="state in ['done', 'error']"`

**Page:**
- Error page: `attrs="{'invisible': [('error_message', '=', False)]}"` → `invisible="not error_message"`

### 2. openclaw_suggestion_views.xml
Fixed 2 instances of `attrs`:

**Header Buttons:**
- `action_accept`: `attrs="{'invisible': [('state', '!=', 'draft')]}"` → `invisible="state != 'draft'"`
- `action_reject`: `attrs="{'invisible': [('state', '!=', 'draft')]}"` → `invisible="state != 'draft'"`

### 3. account_move_views.xml
Fixed 1 instance of `attrs`:

**Header Button:**
- `action_ai_audit`: Complex OR condition converted to direct expression:
  - Old: `attrs="{'invisible': ['|', ('move_type', 'not in', ['out_invoice', 'in_invoice']), ('state', '!=', 'draft')]}"`
  - New: `invisible="move_type not in ['out_invoice', 'in_invoice'] or state != 'draft'"`

### 4. openclaw_config_views.xml
No changes needed - already compatible

## Syntax Reference

### Simple Conditions:
- `attrs="{'invisible': [('field', '=', value)]}"` → `invisible="field == value"`
- `attrs="{'invisible': [('field', '!=', value)]}"` → `invisible="field != value"`

### List Conditions:
- `attrs="{'invisible': [('field', 'in', [a, b])]}"` → `invisible="field in [a, b]"`

### Negation:
- `attrs="{'invisible': [('field', '=', False)]}"` → `invisible="not field"`

### Multiple Conditions (OR):
- `attrs="{'invisible': ['|', ('a', '=', x), ('b', '=', y)]}"` → `invisible="a == x or b == y"`

## Benefits
- Compatible with Odoo 17
- Cleaner, more readable XML
- Better performance (no need to evaluate domain expressions)
- Future-proof

## Verification
✅ All XML files are well-formed
✅ No `attrs` attributes found in any views
✅ All functionality preserved
✅ Module ready for installation

## Module Status
🚀 Ready to install in Odoo 17!
