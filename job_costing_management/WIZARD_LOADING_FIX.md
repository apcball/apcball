# Wizard Loading Fix Summary

## Issue
The module upgrade was failing with:
```
ValueError: External ID not found in the system: job_costing_management.action_job_cost_line_wizard
```

This indicates that wizard actions are being referenced before they are defined in the system.

## Root Causes Identified

### 1. Loading Order Issue
The manifest was loading `job_cost_sheet_views.xml` before `wizard/job_cost_line_wizard_view.xml`, but the views were referencing wizard actions that hadn't been defined yet.

### 2. Missing Security Access
The wizard models were missing from the security access file (`ir.model.access.csv`).

## Solutions Applied

### 1. Fixed Loading Order ✅
Reordered files in `__manifest__.py` to load wizards before views:
```python
# Before
'views/job_cost_sheet_views.xml',  # loaded first
'wizard/job_cost_line_wizard_view.xml',  # loaded later

# After  
'wizard/job_cost_line_wizard_view.xml',  # loaded first
'views/job_cost_sheet_views.xml',  # loaded after wizards
```

### 2. Added Missing Security Access ✅
Added wizard model access rights to `security/ir.model.access.csv`:
```csv
access_job_cost_line_wizard_user,job.cost.line.wizard.user,model_job_cost_line_wizard,group_job_costing_user,1,1,1,0
access_job_cost_line_wizard_manager,job.cost.line.wizard.manager,model_job_cost_line_wizard,group_job_costing_manager,1,1,1,1
access_job_cost_line_bulk_edit_wizard_user,job.cost.line.bulk.edit.wizard.user,model_job_cost_line_bulk_edit_wizard,group_job_costing_user,1,1,1,0
access_job_cost_line_bulk_edit_wizard_manager,job.cost.line.bulk.edit.wizard.manager,model_job_cost_line_bulk_edit_wizard,group_job_costing_manager,1,1,1,1
```

### 3. Temporary Isolation ✅
Temporarily commented out wizard button references in tree view to isolate the loading issue and allow the module to upgrade successfully.

## Files Modified

1. **`__manifest__.py`**: Reordered data files to load wizards before views
2. **`security/ir.model.access.csv`**: Added missing wizard model access rights
3. **`views/job_cost_sheet_views.xml`**: Temporarily commented out wizard buttons

## Next Steps

1. **Test Module Upgrade**: Verify the module now upgrades without errors
2. **Restore Wizard Buttons**: Once the module loads successfully, uncomment the wizard buttons
3. **Test Wizard Functionality**: Verify the wizards work correctly
4. **Final Testing**: Test all job cost line editing features

## Expected Outcome

After these fixes:
- ✅ Module should upgrade without external ID errors
- ✅ All models should be properly loaded
- ✅ Security access should be properly configured
- ✅ Wizard functionality should be available (after uncommenting buttons)

## Verification Commands

After upgrade, verify wizard models exist:
```python
# In Odoo shell
env['job.cost.line.wizard']
env['job.cost.line.bulk.edit.wizard']
```

Both should return model objects without errors.