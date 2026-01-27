# How to Restore Wizard Buttons

## After Successful Module Upgrade

Once the module upgrades successfully, follow these steps to restore the wizard button functionality:

### Step 1: Verify Wizard Models Exist

In Odoo shell or through the interface, verify that the wizard models are properly loaded:

```python
# Check if wizard models exist
env['job.cost.line.wizard']
env['job.cost.line.bulk.edit.wizard']
```

Both should return model objects without errors.

### Step 2: Restore Wizard Buttons

Uncomment the wizard buttons in `views/job_cost_sheet_views.xml`:

**Find this section (around line 286):**
```xml
<!-- Temporarily commented out wizard buttons to isolate loading issues
<header>
    <button name="%(action_job_cost_line_wizard)d" type="action" 
            string="Update Cost Type" class="btn-primary"/>
    <button name="%(action_job_cost_line_bulk_edit_wizard)d" type="action" 
            string="Bulk Edit" class="btn-secondary"/>
</header>
-->
```

**Replace with:**
```xml
<header>
    <button name="%(action_job_cost_line_wizard)d" type="action" 
            string="Update Cost Type" class="btn-primary"/>
    <button name="%(action_job_cost_line_bulk_edit_wizard)d" type="action" 
            string="Bulk Edit" class="btn-secondary"/>
</header>
```

### Step 3: Upgrade Module Again

After uncommenting the buttons, upgrade the module again to load the button functionality.

### Step 4: Test Wizard Functionality

1. **Navigate to Job Cost Lines**: Go to Job Costing → Job Cost Lines
2. **Select Multiple Lines**: Select multiple job cost lines in the tree view
3. **Test Update Cost Type**: Click "Update Cost Type" button and verify the wizard opens
4. **Test Bulk Edit**: Click "Bulk Edit" button and verify the wizard opens
5. **Test Functionality**: Perform actual updates and verify they work correctly

### Step 5: Verify Integration

Test the complete workflow:
1. Create a job cost sheet
2. Add cost lines of different types
3. Use the wizard buttons to bulk edit
4. Verify changes are applied correctly
5. Check that tracking/logging works

## Expected Results

After restoring the buttons:
- ✅ "Update Cost Type" wizard should work for changing cost types
- ✅ "Bulk Edit" wizard should work for updating multiple fields
- ✅ All validations should work correctly
- ✅ Success notifications should appear
- ✅ Changes should be tracked in the chatter

## Troubleshooting

If issues occur after restoring buttons:

1. **Check Odoo Logs**: Look for any error messages
2. **Verify Security**: Ensure user has proper access rights
3. **Test Individual Wizards**: Test each wizard separately
4. **Check Context**: Verify active_ids are passed correctly

## Alternative Approach

If wizard buttons still cause issues, you can add them as separate menu items instead:

1. Create menu items for the wizards in `views/job_costing_menu.xml`
2. Remove the header buttons from the tree view
3. Access wizards through the menu instead

This provides the same functionality with a different user interface approach.