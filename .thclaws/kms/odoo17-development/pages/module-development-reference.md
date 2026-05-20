---
- skill: //odoo17-module-developer
category: reference
created: 2026-05-15
sources: 
tags: [odoo17, module, development, patterns]
title: Odoo 17 Module Development Reference
topic: Complete reference for creating and modifying Odoo 17 modules — models, views, security, wizards, sequences, and Odoo 17–specific view syntax.
updated: 2026-05-15
---

# Odoo 17 Module Development Reference
Description: Complete reference for creating and modifying Odoo 17 modules — models, views, security, wizards, sequences, and Odoo 17–specific view syntax.
---

## Module Structure

```
my_module/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── my_model.py
├── views/
│   └── my_model_views.xml
├── security/
│   ├── ir.model.access.csv
│   └── my_module_security.xml
├── data/
│   └── my_module_data.xml
├── wizard/
│   ├── __init__.py
│   └── my_wizard.py
├── report/
│   └── my_report.xml
└── static/
    └── description/
        └── icon.png
```

## `__manifest__.py`

```python
{
    'name': 'My Module',
    'version': '17.0.1.0.0',
    'summary': 'Short description',
    'description': 'Long description',
    'author': 'Author Name',
    'website': 'https://example.com',
    'category': 'Uncategorized',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/my_module_security.xml',
        'views/my_model_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
}
```

- `version` format: `17.0.major.minor.hotfix`
- `depends` must list every module whose models/views you reference
- `data` must list every XML/CSV file in load order (security before views)

## Models

### New Model

```python
from odoo import api, fields, models

class MyModel(models.Model):
    _name = 'my.module.model'
    _description = 'My Model'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True, tracking=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    partner_id = fields.Many2one('res.partner', string='Partner', ondelete='restrict')
    tag_ids = fields.Many2many('my.module.tag', 'my_model_tag_rel', 'model_id', 'tag_id', string='Tags')
    line_ids = fields.One2many('my.module.line', 'model_id', string='Lines')

    total_amount = fields.Float(string='Total', compute='_compute_total_amount', store=True)

    @api.depends('line_ids.amount')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = sum(record.line_ids.mapped('amount'))

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Name must be unique!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code('my.module.model')
        return super().create(vals_list)

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})
```

### Inherit Existing Model

```python
class ResPartner(models.Model):
    _inherit = 'res.partner'
    custom_field = fields.Char(string='Custom Field')
```

## Views

### Form View

```xml
<odoo>
    <record id="view_my_model_form" model="ir.ui.view">
        <field name="name">my.module.model.form</field>
        <field name="model">my.module.model</field>
        <field name="arch" type="xml">
            <form string="My Model">
                <header>
                    <button name="action_confirm" string="Confirm"
                            type="object" class="oe_highlight"
                            invisible="state != 'draft'"/>
                    <button name="action_cancel" string="Cancel"
                            type="object"
                            invisible="state in ('cancelled', 'done')"/>
                    <field name="state" widget="statusbar"
                           statusbar_visible="draft,confirmed,done"/>
                </header>
                <sheet>
                    <div class="oe_button_box" name="button_box"></div>
                    <div class="oe_title">
                        <h1><field name="name" placeholder="Name..."/></h1>
                    </div>
                    <group>
                        <group><field name="partner_id"/><field name="sequence"/></group>
                        <group><field name="total_amount"/><field name="active"/></group>
                    </group>
                    <notebook>
                        <page string="Lines" name="lines">
                            <field name="line_ids">
                                <tree editable="bottom">
                                    <field name="name"/><field name="amount"/>
                                </tree>
                            </field>
                        </page>
                    </notebook>
                </sheet>
                <div class="oe_chatter">
                    <field name="message_follower_ids"/>
                    <field name="activity_ids"/>
                    <field name="message_ids"/>
                </div>
            </form>
        </field>
    </record>
</odoo>
```

### List / Tree View

```xml
<record id="view_my_model_tree" model="ir.ui.view">
    <field name="name">my.module.model.tree</field>
    <field name="model">my.module.model</field>
    <field name="arch" type="xml">
        <tree decoration-danger="state == 'cancelled'" decoration-success="state == 'done'">
            <field name="name"/><field name="partner_id"/>
            <field name="total_amount" sum="Total"/><field name="state"/>
        </tree>
    </field>
</record>
```

### Search View

```xml
<record id="view_my_model_search" model="ir.ui.view">
    <field name="name">my.module.model.search</field>
    <field name="model">my.module.model</field>
    <field name="arch" type="xml">
        <search>
            <field name="name"/><field name="partner_id"/>
            <separator/>
            <filter string="Draft" name="draft" domain="[('state', '=', 'draft')]"/>
            <group expand="0" string="Group By">
                <filter string="Partner" name="group_partner" context="{'group_by': 'partner_id'}"/>
            </group>
        </search>
    </field>
</record>
```

### Action & Menu

```xml
<record id="action_my_model" model="ir.actions.act_window">
    <field name="name">My Models</field>
    <field name="res_model">my.module.model</field>
    <field name="view_mode">tree,form</field>
    <field name="search_view_id" ref="view_my_model_search"/>
</record>
<menuitem id="menu_my_module_root" name="My Module" sequence="10"/>
<menuitem id="menu_my_module_main" name="My Models"
          parent="menu_my_module_root" action="action_my_model" sequence="10"/>
```

### Inherit Existing View

```xml
<record id="view_partner_form_inherit_my_module" model="ir.ui.view">
    <field name="name">res.partner.form.inherit.my_module</field>
    <field name="model">res.partner</field>
    <field name="inherit_id" ref="base.view_partner_form"/>
    <field name="arch" type="xml">
        <field name="phone" position="after">
            <field name="custom_field"/>
        </field>
    </field>
</record>
```

## Odoo 17 View Attributes (CRITICAL)

**Odoo 17 removed `attrs=`.** Use Python expressions directly:

| Need | Expression |
|------|-----------|
| Equals | `state == 'draft'` |
| Not equals | `state != 'done'` |
| In set | `state in ('done', 'cancelled')` |
| Not in set | `state not in ('draft',)` |
| Falsy | `not partner_id` |
| Truthy | `partner_id` |
| AND | `state == 'done' and not notes` |
| OR | `state == 'done' or state == 'cancelled'` |

```xml
<field name="reason" invisible="state != 'draft'"/>
<field name="reason" required="state == 'cancelled'"/>
<field name="amount" readonly="state != 'draft'"/>
<field name="partner_id" column_invisible="parent.state == 'draft'"/>
```

## Security

### `ir.model.access.csv`

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_my_model_user,my.module.model user,model_my_module_model,base.group_user,1,1,1,0
access_my_model_manager,my.module.model manager,model_my_module_model,base.group_system,1,1,1,1
```

`model_id:id` = `model_` + `_name` with `.` → `_`

### Record Rules

```xml
<record id="rule_my_model_own" model="ir.rule">
    <field name="name">My Model: Own Records Only</field>
    <field name="model_id" ref="model_my_module_model"/>
    <field name="groups" eval="[(4, ref('base.group_user'))]"/>
    <field name="domain_force">[('create_uid', '=', user.id)]</field>
</record>
```

## Sequence (Auto-Numbering)

```xml
<record id="sequence_my_model" model="ir.sequence">
    <field name="name">My Model Sequence</field>
    <field name="code">my.module.model</field>
    <field name="prefix">MM/%(year)s/</field>
    <field name="padding">5</field>
</record>
```

## Wizard (Transient Model)

```python
class MyWizard(models.TransientModel):
    _name = 'my.module.wizard'
    _description = 'My Wizard'
    model_id = fields.Many2one('my.module.model', required=True)
    note = fields.Text()

    def action_confirm(self):
        self.model_id.message_post(body=self.note)
        return {'type': 'ir.actions.act_window_close'}
```

## Pre-Install Checklist

- `__init__.py` imports all models
- `__manifest__.py` lists all `data` files and correct `depends`
- `ir.model.access.csv` covers every model
- XML IDs are unique within the module
- `_name` matches `model_id` in access CSV
- Every view has `arch type="xml"`
- Computed fields have `@api.depends`
- No `attrs=` usage (replaced in Odoo 17)

## Common Mistakes

| Problem | Cause | Fix |
|---------|-------|-----|
| `Field 'xxx' does not exist` | Missing field in model | Check `_name` and field name |
| `ir.model.access` error | No access rights | Add entry in `ir.model.access.csv` |
| `Module not found` | Missing `depends` | Update `__manifest__.py` |
| `Constraint violation` | `_sql_constraints` firing | Check for duplicate data |
| Computed field not updating | `store=True` without `@api.depends` | Add all depends |
