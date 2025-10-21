# Part of buz_warranty_rma_management Odoo module.
# See LICENSE file for full copyright and licensing details.

{
    'name': 'Warranty and RMA Management',
    'version': '17.0.1.0.0',
    'license': 'LGPL-3',
    'summary': 'Manage warranty contracts, claims, and RMA processes',
    'description': """
Warranty and RMA Management
===========================

This module provides a complete solution for managing warranty contracts, 
warranty claims, and RMA (Return Merchandise Authorization) processes 
including repair, replacement, and billing for out-of-warranty items.

Key features:
- Warranty templates for products
- Warranty contracts linked to serial/lot numbers
- Complete RMA workflow with repair and replacement options
- Out-of-warranty billing capability
- Multi-company support
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'category': 'Sales/Sales',
    'depends': [
        'stock',
        'repair',
        'sale_management',
        'account',
        'mail',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/sequence.xml',
        'data/mail_templates.xml',
        
        # Views
        'views/menuitems.xml',
        'views/warranty_template_views.xml',
        'views/warranty_contract_views.xml',
        'views/warranty_claim_views.xml',
        'views/claim_cost_line_views.xml',
        'views/repair_views_inherit.xml',
        'views/stock_picking_inherit.xml',
        'views/res_config_settings_views.xml',
        
        # Reports would go here if needed
    ],
    'demo': [
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}