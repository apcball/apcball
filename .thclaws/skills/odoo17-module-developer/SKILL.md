---
name: odoo17-module-developer
description: Odoo 17 custom module development — models, views, security, wizards, QWeb reports, and business logic. Use when creating new modules, extending existing ones, inheriting models, writing XML views, configuring security, or debugging Odoo 17 issues.
whenToUse: When user asks to create or modify an Odoo 17 module, write models/views/security/wizards, inherit or extend existing models, debug Odoo 17 errors, or needs reference patterns for Odoo 17 development.
---

# Odoo 17 Module Developer

You are an Odoo 17 module development expert. Follow these patterns strictly when creating or modifying Odoo 17 modules. The project root for custom addons is the working directory.

## Module Structure

Every new module must follow this layout:

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
│   └── my_module_security.xml        # optional: record rules
├── data/
│   └── my_module_data.xml            # optional: default data, sequences
├── wizard/
│   ├── __init__.py
│   └── my_wizard.py                  # optional: transient models
├── report/
│   └── my_report.xml                 # optional: QWeb reports
└── static/
    └── description/
        └── icon.png                  # optional: module icon
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

Key rules:
- `version` format: `17.0.major.minor.hotfix`
- `depends` must list every module whose models/views you reference
- `data` must list every XML/CSV file in load order (security before views)

## Models

### New Model

```python
from odoo import api, fields, models

class MyModel(models.Model):
    _name = 'my.module.model'          # dots, not underscores
    _description = 'My Model'
    _inherit = ['mail.thread', 'mail.activity.mixin']   # optional
    _order = 'name asc'
    _rec_name = 'name'

    # Basic Fields
    name = fields.Char(string='Name', required=True, tracking=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    # Relational Fields
    partner_id = fields.Many2one(
        'res.partner', string='Partner',
        ondelete='restrict',           # restrict | cascade | set null
    )
    tag_ids = fields.Many2many(
        'my.module.tag',
        'my_model_tag_rel',            # relation table name
        'model_id', 'tag_id',
        string='Tags',
    )
    line_ids = fields.One2many(
        'my.module.line', 'model_id', string='Lines',
    )

    # Computed Fields
    total_amount = fields.Float(
        string='Total', compute='_compute_total_amount', store=True,
    )

    @api.depends('line_ids.amount')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = sum(record.line_ids.mapped('amount'))

    # Selection Field
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)

    # SQL Constraints
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Name must be unique!'),
    ]

    # Python Constraints
    @api.constrains('total_amount')
    def _check_total_amount(self):
        for record in self:
            if record.total_amount < 0:
                raise ValidationError('Total amount cannot be negative.')

    # Onchange
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.name = self.partner_id.name

    # CRUD Override
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code('my.module.model')
        return super().create(vals_list)

    # Action Methods
    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})
```

### Inherit Existing Model

```python
from odoo import fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'           # no _name needed

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
                    <div class="oe_button_box" name="button_box">
                        <!-- smart buttons here -->
                    </div>
                    <div class="oe_title">
                        <h1>
                            <field name="name" placeholder="Name..."/>
                        </h1>
                    </div>
                    <group>
                        <group>
                            <field name="partner_id"/>
                            <field name="sequence"/>
                        </group>
                        <group>
                            <field name="total_amount"/>
                            <field name="active"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Lines" name="lines">
                            <field name="line_ids">
                                <tree editable="bottom">
                                    <field name="name"/>
                                    <field name="amount"/>
                                </tree>
                            </field>
                        </page>
                        <page string="Notes" name="notes">
                            <field name="notes" nolabel="1"/>
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

### List View

```xml
<record id="view_my_model_tree" model="ir.ui.view">
    <field name="name">my.module.model.tree</field>
    <field name="model">my.module.model</field>
    <field name="arch" type="xml">
        <tree string="My Models" decoration-danger="state == 'cancelled'"
              decoration-success="state == 'done'">
            <field name="name"/>
            <field name="partner_id"/>
            <field name="total_amount" sum="Total"/>
            <field name="state"/>
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
            <field name="name"/>
            <field name="partner_id"/>
            <separator/>
            <filter string="Draft" name="draft"
                    domain="[('state', '=', 'draft')]"/>
            <filter string="Confirmed" name="confirmed"
                    domain="[('state', '=', 'confirmed')]"/>
            <filter string="Archived" name="inactive"
                    domain="[('active', '=', False)]"/>
            <group expand="0" string="Group By">
                <filter string="Partner" name="group_partner"
                        context="{'group_by': 'partner_id'}"/>
                <filter string="Status" name="group_state"
                        context="{'group_by': 'state'}"/>
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
    <field name="context">{}</field>
    <field name="domain">[]</field>
</record>

<menuitem id="menu_my_module_root" name="My Module" sequence="10"/>
<menuitem id="menu_my_module_main" name="My Models"
          parent="menu_my_module_root"
          action="action_my_model" sequence="10"/>
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
        <field name="name" position="attributes">
            <attribute name="required">1</attribute>
        </field>
    </field>
</record>
```

## Security

### `ir.model.access.csv`

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_my_model_user,my.module.model user,model_my_module_model,base.group_user,1,1,1,0
access_my_model_manager,my.module.model manager,model_my_module_model,base.group_system,1,1,1,1
```

Rule: `model_id:id` = `model_` + `_name` with `.` replaced by `_`

### Record Rules

```xml
<odoo>
    <record id="rule_my_model_own" model="ir.rule">
        <field name="name">My Model: Own Records Only</field>
        <field name="model_id" ref="model_my_module_model"/>
        <field name="groups" eval="[(4, ref('base.group_user'))]"/>
        <field name="domain_force">[('create_uid', '=', user.id)]</field>
    </record>
</odoo>
```

## Sequence (Auto-Numbering)

```xml
<!-- data/my_module_data.xml -->
<odoo>
    <record id="sequence_my_model" model="ir.sequence">
        <field name="name">My Model Sequence</field>
        <field name="code">my.module.model</field>
        <field name="prefix">MM/%(year)s/</field>
        <field name="padding">5</field>
    </record>
</odoo>
```

```python
# In create():
vals['name'] = self.env['ir.sequence'].next_by_code('my.module.model')
```

## Wizard (Transient Model)

```python
# wizard/my_wizard.py
from odoo import fields, models

class MyWizard(models.TransientModel):
    _name = 'my.module.wizard'
    _description = 'My Wizard'

    model_id = fields.Many2one('my.module.model', required=True)
    note = fields.Text()

    def action_confirm(self):
        self.model_id.message_post(body=self.note)
        return {'type': 'ir.actions.act_window_close'}
```

```xml
<record id="view_my_wizard_form" model="ir.ui.view">
    <field name="name">my.module.wizard.form</field>
    <field name="model">my.module.wizard</field>
    <field name="arch" type="xml">
        <form string="My Wizard">
            <group>
                <field name="model_id"/>
                <field name="note"/>
            </group>
            <footer>
                <button name="action_confirm" string="Confirm"
                        type="object" class="oe_highlight"/>
                <button string="Cancel" class="btn-secondary"
                        special="cancel"/>
            </footer>
        </form>
    </field>
</record>

<record id="action_my_wizard" model="ir.actions.act_window">
    <field name="name">My Wizard</field>
    <field name="res_model">my.module.wizard</field>
    <field name="view_mode">form</field>
    <field name="target">new</field>
</record>
```

## Odoo 17 View Attributes (CRITICAL)

**Odoo 17 removed `attrs=`.** Use attributes directly with Python expressions:

### invisible

```xml
<!-- Hide when state is not draft -->
<field name="reason" invisible="state != 'draft'"/>

<!-- Hide when field is falsy -->
<field name="end_date" invisible="not start_date"/>

<!-- Hide when Many2one not set -->
<field name="child_ids" invisible="not partner_id"/>

<!-- Multiple states -->
<field name="cancel_reason" invisible="state not in ('cancelled', 'refused')"/>

<!-- AND / OR -->
<field name="tax_amount" invisible="not is_taxable or state == 'draft'"/>
<field name="notes" invisible="state == 'done' or state == 'cancelled'"/>

<!-- On groups and pages -->
<group invisible="state == 'draft'">
    <field name="confirm_date"/>
</group>
<page string="Payment Info" invisible="payment_method == 'none'">
    <field name="payment_ref"/>
</page>
```

### required

```xml
<field name="reason" required="state == 'cancelled'"/>
<field name="end_date" required="is_recurring"/>
<field name="name" required="1"/>
```

### readonly

```xml
<field name="amount" readonly="state != 'draft'"/>
<group readonly="state in ('done', 'cancelled')">
    <field name="delivery_date"/>
</group>
```

### column_invisible (tree columns only)

```xml
<tree>
    <field name="partner_id" column_invisible="parent.state == 'draft'"/>
    <field name="cost" column_invisible="context.get('hide_cost', False)"/>
</tree>
```

### Buttons

```xml
<button name="action_confirm" string="Confirm"
        type="object" class="oe_highlight"
        invisible="state != 'draft'"/>
<button name="action_cancel" string="Cancel"
        type="object"
        invisible="state in ('done', 'cancelled')"/>
```

### Expression Syntax

| Need | Expression |
|------|-----------|
| Equals | `state == 'draft'` |
| Not equals | `state != 'done'` |
| In set | `state in ('done', 'cancelled')` |
| Not in set | `state not in ('draft',)` |
| Field is falsy | `not partner_id` |
| Field is truthy | `partner_id` |
| AND | `state == 'done' and not notes` |
| OR | `state == 'done' or state == 'cancelled'` |
| Boolean True | `is_company` |
| Boolean False | `not is_company` |
| Numeric compare | `amount > 0` |

## Python Domain Syntax

```python
# AND (default)
domain = [('state', '=', 'draft'), ('partner_id', '!=', False)]

# OR — use '|' prefix
domain = ['|', ('name', 'ilike', 'test'), ('ref', 'ilike', 'test')]

# Combined
domain = ['&', ('active', '=', True), '|',
          ('name', 'ilike', 'test'), ('ref', 'ilike', 'test')]

# Operators: =, !=, <, >, <=, >=, like, ilike, not ilike, =like, =ilike,
#            in, not in, child_of, parent_of
```

## Common Patterns

### Return Action After Save

```python
def action_open_related(self):
    return {
        'type': 'ir.actions.act_window',
        'name': 'Related Records',
        'res_model': 'my.other.model',
        'view_mode': 'tree,form',
        'domain': [('model_id', '=', self.id)],
        'context': {'default_model_id': self.id},
    }
```

### Smart Button

```xml
<button class="oe_stat_button" type="object"
        name="action_open_related" icon="fa-list">
    <field name="related_count" widget="statinfo" string="Related"/>
</button>
```

```python
related_count = fields.Integer(compute='_compute_related_count')

@api.depends('line_ids')
def _compute_related_count(self):
    for record in self:
        record.related_count = len(record.line_ids)
```

### Sudo (Use Cautiously)

```python
record = self.env['res.partner'].sudo().browse(partner_id)
```

### Context

```python
# Pass to view
{'default_partner_id': self.partner_id.id}

# Read in model
partner_id = self.env.context.get('default_partner_id')
```

## Common Mistakes

| Problem | Cause | Fix |
|---------|-------|-----|
| `Field 'xxx' does not exist` | Missing field in model | Check `_name` and field name |
| `ir.model.access` error | No access rights | Add entry in `ir.model.access.csv` |
| `Module not found` | Missing `depends` | Update `__manifest__.py` |
| View doesn't show field | Missing from XML | Check view XML |
| `Constraint violation` | `_sql_constraints` firing | Check for duplicate data |
| Computed field not updating | `store=True` without `@api.depends` | Add all depends |
| `ondelete` error | Related record deleted | Change ondelete policy |

## Pre-Install Checklist

Before installing any module, verify:
- [ ] `__init__.py` imports all models
- [ ] `__manifest__.py` lists all `data` files and correct `depends`
- [ ] `ir.model.access.csv` covers every model
- [ ] XML IDs are unique within the module
- [ ] `_name` in model matches `model_id` in access CSV (`model_` + dots→underscores)
- [ ] Every view has `arch type="xml"`
- [ ] Computed fields have `@api.depends`
- [ ] No `attrs=` usage (replaced in Odoo 17)

## Odoo CLI

```bash
# Update module
./odoo-bin -u my_module -d my_database

# Install module
./odoo-bin -i my_module -d my_database

# Update all
./odoo-bin -u all -d my_database

# Debug logging
./odoo-bin -u my_module -d my_database --log-level=debug
```
