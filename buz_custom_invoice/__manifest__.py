{
    'name': 'buz_custom Invoice',
    'version': '1.0',
    'category': 'Accounting',
    'summary': 'Custom Invoice Report and Fields',
    'description': """
        Custom Invoice Report and Additional Fields for Odoo 17
        Features:
        - Custom invoice report layout
        - Additional fields for invoices
        - Customized totals calculation
    """,
    'author': 'Your Name',
    'website': 'https://www.yourwebsite.com',
    'depends': ['base', 'account', 'purchase', 'stock', 'sale_management'],
    'data': [
        'security/security.xml',           # เพิ่มไฟล์ security.xml
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/account_move_views.xml',
        'report/paperformat.xml',
        'report/invoice_template.xml',
        'report/report_action.xml',
        'report/ecommerce_receipt_report.xml',
        'report/cerdit_note.xml',
        'report/invoice_tax.xml',
        'report/vendor_credit_note.xml',
    
        
     ],  
     'assets': {
        'web.report_assets_common': [
            '/buz_custom_invoice/static/fonts/Sarabun-Regular.ttf',
        ],
    }, 
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}