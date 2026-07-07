{
    'name': 'Custom Delivery Report',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Custom delivery, receipt & transfer slip reports',
    'description': """
        This module customizes the delivery, receipt and transfer report templates in Odoo.
        Features:
        - Custom delivery slip design (ใบส่งสินค้า / Delivery Slip)
        - Custom receipt slip design (ใบรับสินค้า / Receipt Slip) with amounts
        - Custom transfer slip design (ใบโอนสินค้า / Transfer Slip)
        - Auto-detects picking type and switches template layout
        - Additional information on all reports
        - Enhanced layout and formatting
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['stock', 'delivery', 'purchase', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'reports/delivery_report.xml',
        'reports/receipt_report.xml',
        'reports/reciept_request_report.xml',
        'views/report_menu.xml',
    ],
    'images': ['static/description/icon.png'],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
