{
    'name': 'Inventory Delivery Report',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Custom delivery report for inventory operations',
    'description': """
        This module adds a custom delivery report to the inventory module.
        Features:
        - Detailed delivery report for stock picking operations
        - Enhanced layout and information display
        - Compatible with Odoo 17 inventory operations
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'report/delivery_report_template.xml',
        'report/delivery_report.xml',
        'report/distributor_delivery_note.xml',
        'report/distributor_delivery_export.xml',
        'report/delivery_note_report.xml',
        'report/dispatch_report.xml',
        'report/borrow_equipment_form.xml',
        'report/request_borrow_equipment_form.xml',
        'report/request_change_products.xml',
        'report/request_job_order.xml',
        'report/delivery_report_tem.xml',

    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}