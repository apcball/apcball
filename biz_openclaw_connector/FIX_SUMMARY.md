# Fix Summary - biz_openclaw_connector

## Issue
The module failed to install with the following error:
```
KeyError: <function AccountMove.<lambda> at 0x743be2f61fc0>
```

## Root Cause
The One2many field definitions in the AccountMove model were incorrectly using lambda functions as the `inverse_name` parameter:

```python
openclaw_job_ids = fields.One2many('openclaw.job', lambda self: self._get_openclaw_jobs_domain(), string='OpenClaw Jobs')
```

This is invalid because the second parameter of `One2many` must be the name of the Many2one field on the related model that points back to this model, not a lambda function.

## Solution
Added proper Many2one relationship fields and updated the One2many definitions:

### 1. Updated AccountMove model
Changed from invalid lambda-based One2many to proper field references:

```python
openclaw_job_ids = fields.One2many('openclaw.job', 'move_id', string='OpenClaw Jobs')
openclaw_suggestion_ids = fields.One2many('openclaw.suggestion', 'move_id', string='OpenClaw Suggestions')
```

### 2. Added move_id field to openclaw.job
```python
move_id = fields.Many2one('account.move', string='Invoice', ondelete='cascade', help='Related invoice if model is account.move')
```

### 3. Added move_id field to openclaw.suggestion
```python
move_id = fields.Many2one('account.move', string='Invoice', ondelete='cascade', help='Related invoice if model is account.move')
```

### 4. Updated openclaw.job.create_job()
Now sets move_id when creating jobs for account.move:

```python
if model_name == 'account.move':
    vals['move_id'] = record_id
```

### 5. Updated openclaw.suggestion.create_from_response()
Now sets move_id when creating suggestions for account.move:

```python
if job.model_name == 'account.move':
    vals['move_id'] = job.record_id
```

## Benefits
- Proper Odoo ORM relationships
- Direct database foreign keys
- Better performance (no need for search-based computed fields)
- Standard One2many/Many2one pattern
- Clean cascade delete behavior

## Files Modified
1. `models/account_move.py` - Fixed One2many definitions
2. `models/openclaw_job.py` - Added move_id field and updated create_job()
3. `models/openclaw_suggestion.py` - Added move_id field and updated create_from_response()

## Module Status
✅ Ready for installation
✅ Follows Odoo 17 best practices
✅ Proper ORM relationships
✅ All functionality preserved
