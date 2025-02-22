{
    'name': 'Billing Note Management',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'จัดการใบวางบิล',
    'description': """
        โมดูลสำหรับจัดการใบวางบิล
        - สร้างใบวางบิล
        - ติดตามสถานะการชำระเงิน
        - พิมพ์รายงานใบวางบิล
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'mail',
        'account',
    ],
    'data': [
        'security/billing_note_security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'wizards/add_bills_wizard_views.xml',
        'views/billing_note_views.xml',
        'views/account_move_views.xml',
        'report/billing_note_report.xml',
        'report/billing_note_report_template.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'icon': '/buz_costom_billing_note/static/description/icon.png',
}