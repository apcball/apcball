# Technical Specifications for Warranty Manual Creation

## 1. Sale Order Model Extension

### File: `models/sale_order.py`
```python
from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    warranty_card_ids = fields.One2many(
        'warranty.card', 
        'sale_order_id', 
        string='Warranty Cards'
    )
    warranty_card_count = fields.Integer(
        string='Warranty Cards Count',
        compute='_compute_warranty_card_count'
    )
    
    def _compute_warranty_card_count(self):
        for order in self:
            order.warranty_card_count = len(order.warranty_card_ids)
    
    def action_create_warranty_card(self):
        """Create warranty cards for delivered products with warranty"""
        self.ensure_one()
        
        # Check if order is delivered
        if self.state not in ['done', 'sale']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': 'Order must be confirmed to create warranty cards',
                    'type': 'warning',
                }
            }
        
        # Get delivered pickings
        delivered_pickings = self.picking_ids.filtered(
            lambda p: p.state == 'done' and p.picking_type_code == 'outgoing'
        )
        
        if not delivered_pickings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No delivered products found for warranty creation',
                    'type': 'info',
                }
            }
        
        # Create warranty cards
        warranty_cards = self._create_warranty_cards_from_pickings(delivered_pickings)
        
        if warranty_cards:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Created Warranty Cards',
                'res_model': 'warranty.card',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', warranty_cards.ids)],
                'context': {'create': False},
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No products with warranty configuration found',
                    'type': 'info',
                }
            }
    
    def _create_warranty_cards_from_pickings(self, pickings):
        """Create warranty cards from delivered pickings"""
        WarrantyCard = self.env['warranty.card']
        warranty_cards = WarrantyCard
        
        for picking in pickings:
            for move_line in picking.move_line_ids:
                product = move_line.product_id
                
                # Check if product has warranty configuration
                if (product.product_tmpl_id.warranty_duration <= 0):
                    continue
                
                # Check if warranty card already exists
                existing = WarrantyCard.search([
                    ('sale_order_id', '=', self.id),
                    ('product_id', '=', product.id),
                    ('lot_id', '=', move_line.lot_id.id if move_line.lot_id else False),
                ], limit=1)
                
                if existing:
                    continue
                
                # Create warranty card
                warranty_vals = {
                    'partner_id': self.partner_id.id,
                    'product_id': product.id,
                    'lot_id': move_line.lot_id.id if move_line.lot_id else False,
                    'start_date': picking.date_done.date() if picking.date_done else fields.Date.today(),
                    'sale_order_id': self.id,
                    'picking_id': picking.id,
                    'state': 'active',
                }
                
                warranty_card = WarrantyCard.create(warranty_vals)
                warranty_cards += warranty_card
                
                # Post message on picking
                picking.message_post(
                    body=f'Warranty card {warranty_card.name} created for product {product.display_name}',
                    subject='Warranty Card Created'
                )
        
        return warranty_cards
    
    def action_view_warranty_cards(self):
        """View warranty cards related to this sale order"""
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_card').read()[0]
        action['domain'] = [('sale_order_id', '=', self.id)]
        action['context'] = {
            'default_partner_id': self.partner_id.id,
            'default_sale_order_id': self.id,
        }
        return action
```

## 2. Sale Order View Extension

### File: `views/sale_order_views.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    
    <!-- Sale Order Form View Inherit -->
    <record id="view_sale_order_form_inherit_warranty" model="ir.ui.view">
        <field name="name">sale.order.form.inherit.warranty</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">
            
            <!-- Add Create Warranty Card button in header -->
            <xpath expr="//button[@name='action_view_invoice']" position="after">
                <button name="action_create_warranty_card" 
                        string="Create Warranty Card" 
                        type="object" 
                        class="btn-primary"
                        attrs="{'invisible': [('state', 'not in', ['sale', 'done'])]}"/>
            </xpath>
            
            <!-- Add warranty cards smart button -->
            <xpath expr="//div[@name='button_box']" position="inside">
                <button name="action_view_warranty_cards" 
                        type="object" 
                        class="oe_stat_button" 
                        icon="fa-shield"
                        attrs="{'invisible': [('warranty_card_count', '=', 0)]}">
                    <field name="warranty_card_count" widget="statinfo" string="Warranty Cards"/>
                </button>
            </xpath>
            
        </field>
    </record>

</odoo>
```

## 3. Product Template View Modifications

### Modified File: `views/product_template_views.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    
    <!-- Product Template Form View Inherit -->
    <record id="view_product_template_form_inherit_warranty" model="ir.ui.view">
        <field name="name">product.template.form.inherit.warranty</field>
        <field name="model">product.template</field>
        <field name="inherit_id" ref="product.product_template_form_view"/>
        <field name="arch" type="xml">
            
            <xpath expr="//notebook" position="inside">
                <page string="Warranty Information" name="warranty">
                    <group>
                        <group string="Warranty Configuration">
                            <!-- REMOVED: auto_warranty checkbox -->
                            <label for="warranty_duration" string="Warranty Period"/>
                            <div>
                                <field name="warranty_duration" class="oe_inline" style="width: 60px;"/>
                                <field name="warranty_period_unit" class="oe_inline" style="width: 120px;"/>
                            </div>
                            <field name="warranty_type"/>
                        </group>
                        <group string="Out-of-Warranty Settings">
                            <field name="allow_out_of_warranty"/>
                            <field name="service_product_id" invisible="allow_out_of_warranty == False"/>
                        </group>
                    </group>
                    <group string="Warranty Terms & Conditions">
                        <field name="warranty_condition" nolabel="1"/>
                    </group>
                </page>
            </xpath>
            
            <xpath expr="//div[@name='button_box']" position="inside">
                <button name="action_view_warranty_cards" type="object"
                        class="oe_stat_button" icon="fa-shield"
                        invisible="warranty_card_count == 0">
                    <field name="warranty_card_count" widget="statinfo" string="Warranties"/>
                </button>
            </xpath>
            
        </field>
    </record>

</odoo>
```

## 4. Product Template Model Modifications

### Modified File: `models/product_template.py`
```python
from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    warranty_duration = fields.Integer(
        string='Warranty Duration',
        default=0,
        help='Warranty period from delivery date'
    )
    warranty_period_unit = fields.Selection([
        ('month', 'Month(s)'),
        ('year', 'Year(s)'),
    ], string='Period Unit', default='month', help='Unit for warranty duration')
    warranty_condition = fields.Text(
        string='Warranty Terms & Conditions',
        help='Terms and conditions applicable to this warranty'
    )
    warranty_type = fields.Selection([
        ('replacement', 'Replacement'),
        ('repair', 'Repair'),
        ('refund', 'Refund'),
    ], string='Warranty Type', default='repair')
    # REMOVED: auto_warranty field
    service_product_id = fields.Many2one(
        'product.product',
        string='Service Product',
        domain=[('type', '=', 'service')],
        help='Service product used for out-of-warranty repairs'
    )
    allow_out_of_warranty = fields.Boolean(
        string='Allow Out-of-Warranty Service',
        default=True,
        help='Allow creating quotations for expired warranty claims'
    )
    warranty_card_count = fields.Integer(
        string='Warranty Cards',
        compute='_compute_warranty_card_count'
    )

    def _compute_warranty_card_count(self):
        for record in self:
            record.warranty_card_count = self.env['warranty.card'].search_count([
                ('product_id.product_tmpl_id', '=', record.id)
            ])

    def action_view_warranty_cards(self):
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_card').read()[0]
        action['domain'] = [('product_id.product_tmpl_id', '=', self.id)]
        action['context'] = {'default_product_id': self.product_variant_id.id}
        return action
```

## 5. Stock Picking Model Modifications

### Modified File: `models/stock_picking.py`
```python
from odoo import models, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # REMOVED: automatic warranty card creation
        res = super(StockPicking, self).button_validate()
        # REMOVED: self._create_warranty_cards()
        return res

    # KEPT for potential future use but not called automatically
    def _create_warranty_cards(self):
        """This method is kept for compatibility but not called automatically"""
        WarrantyCard = self.env['warranty.card']
        
        for picking in self:
            if picking.picking_type_code != 'outgoing' or picking.state != 'done':
                continue
            
            sale_order = picking.sale_id
            partner = picking.partner_id
            
            for move_line in picking.move_line_ids:
                product = move_line.product_id
                
                # REMOVED: auto_warranty check
                if product.product_tmpl_id.warranty_duration <= 0:
                    continue
                
                existing_warranty = WarrantyCard.search([
                    ('picking_id', '=', picking.id),
                    ('product_id', '=', product.id),
                    ('lot_id', '=', move_line.lot_id.id if move_line.lot_id else False),
                ], limit=1)
                
                if existing_warranty:
                    continue
                
                warranty_vals = {
                    'partner_id': partner.id,
                    'product_id': product.id,
                    'lot_id': move_line.lot_id.id if move_line.lot_id else False,
                    'start_date': picking.date_done.date() if picking.date_done else picking.scheduled_date,
                    'sale_order_id': sale_order.id if sale_order else False,
                    'picking_id': picking.id,
                    'state': 'active',
                }
                
                warranty_card = WarrantyCard.create(warranty_vals)
                
                picking.message_post(
                    body=f'Warranty card {warranty_card.name} created for product {product.display_name}',
                    subject='Warranty Card Created'
                )
        
        return True
```

## 6. Manifest File Updates

### Modified File: `__manifest__.py`
```python
{
    'name': 'Warranty Management',
    'version': '17.0.1.1.0',
    'category': 'Sales/Warranty',
    'summary': 'Complete Warranty Management System with Claims and Certificate Generation',
    'description': """
        Warranty Management System
        ===========================
        * Product-level warranty configuration
        * Manual warranty card creation from Sale Order
        * Warranty claim management (under & out-of-warranty)
        * RMA workflows with stock operations
        * Claim lines for parts and consumables tracking
        * RMA IN/OUT pickings with serial/lot support
        * Multi-product RMA IN returns with part selection
        * Replacement issue with SO integration
        * Quick invoice generation from claim lines
        * Out-of-warranty quotation generation
        * Warranty certificate and RMA slip printing
        * Configurable locations, accounts, and operation types
        * Dashboard and reporting
    """,
    'author': 'apcball',
    'website': 'https://www.buzzit.co.th',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'stock',
        'stock_account',
        'account',
        'mail',
        'uom',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_warranty_management/static/src/scss/warranty_styles.scss',
            'buz_warranty_management/static/src/scss/dashboard_indicators.scss',
            'buz_warranty_management/static/src/js/dashboard_auto_refresh.js',
        ],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',  # ADDED
        'views/warranty_card_views.xml',
        'views/warranty_claim_views.xml',
        'views/warranty_dashboard_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/warranty_out_wizard_view.xml',
        'wizard/warranty_rma_receive_wizard_view.xml',
        'wizard/warranty_replacement_issue_wizard_view.xml',
        'wizard/warranty_invoice_wizard_view.xml',
        'report/report_warranty_certificate.xml',
        'report/report_warranty_claim_form.xml',
        'report/report_warranty_rma_slip.xml',
        'data/warranty_dashboard_cron.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
```

## 7. Model Initialization Update

### Modified File: `models/__init__.py`
```python
from . import product_template
from . import product
from . import warranty_card
from . import warranty_claim
from . import warranty_claim_line
from . import warranty_dashboard
from . import warranty_dashboard_cache
from . import res_config_settings
from . import res_partner
from . import sale_order  # ADDED
from . import stock_picking