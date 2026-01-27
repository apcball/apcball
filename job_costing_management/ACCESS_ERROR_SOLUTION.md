# BOQ Material Requisition Wizard - Access Error Solution

## Problem
Users are getting an access error when trying to use the BOQ Material Requisition Wizard:
```
Access Error
You are not allowed to access 'BOQ Material Requisition Wizard' (boq.material.requisition.wizard) records.
No group currently allows this operation.
Contact your administrator to request access if necessary.
```

## Root Cause
The new BOQ Material Requisition Wizard models were missing proper access rights in the security configuration.

## Solution Implemented

### 1. Added Access Rights to `security/ir.model.access.csv`

Added the following access rights for the wizard models:

```csv
# BOQ Material Requisition Wizard Access Rights
access_boq_material_requisition_wizard_user,boq.material.requisition.wizard.user,model_boq_material_requisition_wizard,group_job_costing_user,1,1,1,0
access_boq_material_requisition_wizard_manager,boq.material.requisition.wizard.manager,model_boq_material_requisition_wizard,group_job_costing_manager,1,1,1,1
access_boq_material_requisition_wizard_material_user,boq.material.requisition.wizard.material.user,model_boq_material_requisition_wizard,group_material_requisition_user,1,1,1,0
access_boq_material_requisition_wizard_material_manager,boq.material.requisition.wizard.material.manager,model_boq_material_requisition_wizard,group_material_requisition_manager,1,1,1,1
access_boq_material_requisition_wizard_line_user,boq.material.requisition.wizard.line.user,model_boq_material_requisition_wizard_line,group_job_costing_user,1,1,1,0
access_boq_material_requisition_wizard_line_manager,boq.material.requisition.wizard.line.manager,model_boq_material_requisition_wizard_line,group_job_costing_manager,1,1,1,1
access_boq_material_requisition_wizard_line_material_user,boq.material.requisition.wizard.line.material.user,model_boq_material_requisition_wizard_line,group_material_requisition_user,1,1,1,0
access_boq_material_requisition_wizard_line_material_manager,boq.material.requisition.wizard.line.material.manager,model_boq_material_requisition_wizard_line,group_material_requisition_manager,1,1,1,1
access_boq_material_requisition_wizard_base,boq.material.requisition.wizard.base,model_boq_material_requisition_wizard,base.group_user,1,1,1,0
access_boq_material_requisition_wizard_line_base,boq.material.requisition.wizard.line.base,model_boq_material_requisition_wizard_line,base.group_user,1,1,1,0
```

### 2. Security Groups with Access

The following security groups now have access to the wizard:

- **Job Costing User** (`group_job_costing_user`) - Read, Write, Create
- **Job Costing Manager** (`group_job_costing_manager`) - Read, Write, Create, Delete
- **Material Requisition User** (`group_material_requisition_user`) - Read, Write, Create
- **Material Requisition Manager** (`group_material_requisition_manager`) - Read, Write, Create, Delete
- **Base User** (`base.group_user`) - Read, Write, Create (fallback)

### 3. Debug Tools Added

Added debugging tools to help troubleshoot access issues:

1. **Debug Button** in BOQ form (visible to Technical Features users)
2. **Test Scripts** for verifying access rights
3. **SQL Verification Script** for database-level checking

## How to Fix the Access Error

### Step 1: Update the Module
```bash
# In Odoo, go to Apps > Job Costing Management > Update
# Or via command line:
./odoo-bin -u job_costing_management -d your_database
```

### Step 2: Assign User to Correct Group
1. Go to **Settings > Users & Companies > Users**
2. Select the user experiencing the error
3. In the **Access Rights** tab, ensure the user is assigned to one of:
   - Job Costing User
   - Job Costing Manager
   - Material Requisition User
   - Material Requisition Manager

### Step 3: Verify Access (Optional)
1. Open a BOQ in approved state
2. Click the "Debug Wizard Access" button (if you have Technical Features enabled)
3. Check the notification for access status

### Step 4: Clear Cache and Restart
1. Clear browser cache
2. Restart Odoo server if needed
3. Try accessing the wizard again

## Verification Steps

### 1. Check User Groups
```sql
-- Run in database to check user groups
SELECT 
    u.login,
    rg.name as group_name
FROM res_users u
JOIN res_groups_users_rel rgur ON u.id = rgur.uid
JOIN res_groups rg ON rgur.gid = rg.id
WHERE u.login = 'your_username'
  AND (rg.name LIKE '%Job Costing%' OR rg.name LIKE '%Material Requisition%');
```

### 2. Check Access Rights
```sql
-- Run in database to verify access rights exist
SELECT 
    ima.name,
    im.model,
    rg.name as group_name,
    ima.perm_read,
    ima.perm_write,
    ima.perm_create
FROM ir_model_access ima
JOIN ir_model im ON ima.model_id = im.id
LEFT JOIN res_groups rg ON ima.group_id = rg.id
WHERE im.model = 'boq.material.requisition.wizard';
```

### 3. Test Wizard Access
1. Open an approved BOQ
2. Click "Create Material Requisition" button
3. Wizard should open without errors

## Expected Workflow After Fix

1. **Create/Approve BOQ** with products and quantities
2. **Click "Create Material Requisition"** button
3. **Wizard opens** showing BOQ lines with remaining quantities
4. **Select lines** and adjust quantities as needed
5. **Click "Create Requisition"** to generate material requisition
6. **Material requisition created** and opened for further processing

## Troubleshooting

### If Error Persists:

1. **Check Module Installation**
   - Ensure job_costing_management module is properly installed
   - Update the module to reload security rules

2. **Check Database Integrity**
   - Run the SQL verification script
   - Ensure access rights are properly loaded

3. **Check User Permissions**
   - Verify user has required group assignments
   - Check if user has Technical Features enabled (if needed)

4. **Check System Configuration**
   - Restart Odoo server
   - Clear all caches
   - Check Odoo logs for detailed error messages

### Common Issues:

1. **"No BOQ lines found"** - BOQ has no lines with remaining quantities
2. **"Wizard not opening"** - BOQ not in approved/locked state
3. **"Action not found"** - Module not properly updated
4. **"Permission denied"** - User not in correct security group

## Support

If the issue persists after following these steps:

1. Check Odoo server logs for detailed error messages
2. Verify module dependencies are satisfied
3. Ensure database has been properly updated
4. Contact system administrator for advanced troubleshooting

## Files Modified

- `security/ir.model.access.csv` - Added wizard access rights
- `models/boq.py` - Added debug method
- `views/boq_views.xml` - Added debug button
- `test_wizard_access.py` - Created test script
- `verify_access_rights.sql` - Created verification script