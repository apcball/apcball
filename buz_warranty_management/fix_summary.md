# Fix for TypeError: "Determination requires a callable or method name"

## Problem Identified
The error was caused by four search methods in `models/warranty_card.py` that were missing the `@api.model` decorator:
- `_search_claim_count`
- `_search_days_remaining` 
- `_search_days_since_expiry`
- `_search_last_claim_date`

## Root Cause
When a compute field has `search=True`, Odoo requires a corresponding search method with the `@api.model` decorator. Without this decorator, the methods are treated as instance methods instead of model methods, causing the "Determination requires a callable or method name" error when Odoo tries to use them for domain filtering.

## Fix Applied
Added `@api.model` decorator to all four search methods:

```python
@api.model
def _search_claim_count(self, operator, value):
    # ... existing code ...

@api.model  
def _search_days_remaining(self, operator, value):
    # ... existing code ...

@api.model
def _search_days_since_expiry(self, operator, value):
    # ... existing code ...

@api.model
def _search_last_claim_date(self, operator, value):
    # ... existing code ...
```

## Verification
The fix has been applied to the file `/opt/instance1/odoo17/custom-addons/buz_warranty_management/models/warranty_card.py`.

## Next Steps Required
Since Odoo server is still running, the changes need to be applied by either:

1. **Restarting the Odoo server** (recommended)
2. **Upgrading the module** through Odoo interface:
   - Go to Apps → Update Apps List
   - Find "Warranty Management" 
   - Click Upgrade
   - Restart server afterwards

## Files Modified
- `buz_warranty_management/models/warranty_card.py` (lines 203, 227, 255, 283)

## Expected Result
After applying the fix, the TypeError should be resolved and warranty card search/filtering operations should work correctly in the web interface.