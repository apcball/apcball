# BUZ Validate Control Module - Implementation Guide

## 1. Module Manifest (__manifest__.py)

```python
# -*- coding: utf-8 -*-
{
    "name": "BUZ Validate Control",
    "summary": "Control access to Validate/Post buttons in Stock and Account documents",
    "version": "17.0.1.0.0",
    "category": "Extra Tools",
    "author": "BUZ Team",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "account",
        "base",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/stock_picking_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
```

## 2. Security Configuration

### security/security.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="0">
        <!-- Create category for validate control -->
        <record id="module_category_validate_control" model="ir.module.category">
            <field name="name">Validate Control</field>
            <field name="description">Control document validation permissions</field>
            <field name="sequence">25</field>
        </record>

        <!-- Validate Privileged Group -->
        <record id="group_validate_privileged" model="res.groups">
            <field name="name">Validate Privileged</field>
            <field name="category_id" ref="module_category_validate_control"/>
            <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
            <field name="comment">Users who can validate/post documents</field>
        </record>
    </data>
</odoo>
```

### security/ir.model.access.csv
```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_validate_privileged_group,res.groups.validate.privileged,base.model_res_groups,buz_validate_control.group_validate_privileged,1,0,0,0
```

## 3. Model Overrides

### models/__init__.py
```python
# -*- coding: utf-8 -*-
from . import stock_picking
from . import account_move
```

### models/stock_picking.py
```python
# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import AccessError

class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        """Override to add security check for validation"""
        if not self.env.user.has_group('buz_validate_control.group_validate_privileged'):
            raise AccessError(_("You don't have permission to validate stock transfers. Please contact your administrator."))
        
        return super(StockPicking, self).button_validate()
```

### models/account_move.py
```python
# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import AccessError

class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        """Override to add security check for posting"""
        if not self.env.user.has_group('buz_validate_control.group_validate_privileged'):
            raise AccessError(_("You don't have permission to post journal entries. Please contact your administrator."))
        
        return super(AccountMove, self).action_post()
```

## 4. View Modifications

### views/stock_picking_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Inherit stock picking form to add groups attribute to Validate button -->
    <record id="view_picking_form_inherit_validate_control" model="ir.ui.view">
        <field name="name">stock.picking.form.inherit.validate.control</field>
        <field name="model">stock.picking</field>
        <field name="inherit_id" ref="stock.view_picking_form"/>
        <field name="arch" type="xml">
            <!-- Add groups attribute to Validate button -->
            <xpath expr="//button[@name='button_validate']" position="attributes">
                <attribute name="groups">buz_validate_control.group_validate_privileged</attribute>
            </xpath>
            
            <!-- Also handle the Validate button in smart buttons if it exists -->
            <xpath expr="//button[@name='action_done']" position="attributes">
                <attribute name="groups">buz_validate_control.group_validate_privileged</attribute>
            </xpath>
        </field>
    </record>
</odoo>
```

### views/account_move_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Inherit account move form to add groups attribute to Post button -->
    <record id="view_move_form_inherit_validate_control" model="ir.ui.view">
        <field name="name">account.move.form.inherit.validate.control</field>
        <field name="model">account.move</field>
        <field name="inherit_id" ref="account.view_move_form"/>
        <field name="arch" type="xml">
            <!-- Add groups attribute to Post button -->
            <xpath expr="//button[@name='action_post']" position="attributes">
                <attribute name="groups">buz_validate_control.group_validate_privileged</attribute>
            </xpath>
        </field>
    </record>
</odoo>
```

## 5. Module Structure Files

### __init__.py (root)
```python
# -*- coding: utf-8 -*-
from . import models
```

### models/__init__.py
```python
# -*- coding: utf-8 -*-
from . import stock_picking
from . import account_move
```

### security/__init__.py
```python
# -*- coding: utf-8 -*-
```

## 6. Documentation

### README.md
```markdown
# BUZ Validate Control Module

## Description
This module provides control over who can validate/post documents in Odoo by restricting access to Validate and Post buttons.

## Features
- Hides Validate button in Stock Picking for unauthorized users
- Hides Post button in Account Move for unauthorized users
- Server-side security checks prevent bypassing UI restrictions
- Simple group-based permission management

## Installation
1. Copy the module to your Odoo addons directory
2. Update your module list
3. Install the module from Apps menu

## Configuration
1. Go to Settings > Users & Companies > Groups
2. Find the "Validate Privileged" group under "Validate Control" category
3. Add users who should have validation permissions to this group

## Usage
- Users in the "Validate Privileged" group will see and can use Validate/Post buttons
- Users not in this group will not see these buttons
- Direct API calls are also protected by server-side checks

## Technical Details
- Module overrides `button_validate()` method of `stock.picking`
- Module overrides `action_post()` method of `account.move`
- Uses Odoo's standard group-based security system
- Provides dual-layer protection (UI and server-side)

## Version
17.0.1.0.0

## License
LGPL-3
```

## 7. Testing Checklist

### Functional Testing
- [ ] Users without privileges cannot see Validate button in Stock Picking
- [ ] Users without privileges cannot see Post button in Account Move
- [ ] Users with privileges can see and use Validate button
- [ ] Users with privileges can see and use Post button
- [ ] Server-side protection works even if UI is bypassed

### Security Testing
- [ ] Direct API call to button_validate() fails for unauthorized users
- [ ] Direct API call to action_post() fails for unauthorized users
- [ ] Proper error messages are displayed
- [ ] No security loopholes in group inheritance

### UI Testing
- [ ] Buttons are properly hidden in form views
- [ ] Buttons are properly hidden in list views (if applicable)
- [ ] No layout issues when buttons are hidden
- [ ] Responsive design works correctly

## 8. Deployment Notes

### Before Deployment
1. Test thoroughly in development environment
2. Verify no conflicts with existing customizations
3. Ensure all users who need access are identified

### After Deployment
1. Add appropriate users to the "Validate Privileged" group
2. Communicate changes to affected users
3. Monitor for any issues or access requests
4. Document any business process changes

## 9. Troubleshooting

### Common Issues
1. **Users still see buttons**: Clear browser cache and restart Odoo server
2. **Access denied error**: Ensure user is added to the correct group
3. **Module installation fails**: Check dependencies and Odoo version compatibility

### Debug Steps
1. Check user groups in Settings > Users
2. Verify module is installed and up to date
3. Check browser console for JavaScript errors
4. Review Odoo server logs for any errors