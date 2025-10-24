{
    'name': 'Warranty Management',
    'version': '17.0.1.0.0',
    'category': 'Sales/Warranty',
    'summary': 'Complete Warranty Management System with Claims and Certificate Generation',
    'description': """
        Warranty Management System
        ===========================
        * Product-level warranty configuration
        * Automatic warranty card creation on delivery
        * Warranty claim management (under & out-of-warranty)
        * Out-of-warranty quotation generation
        * Warranty certificate printing
        * Dashboard and reporting
    """,
    'author': 'Buzzit',
    'website': 'https://www.buzzit.co.th',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'stock',
        'account',
        'mail',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/product_template_views.xml',
        'views/warranty_card_views.xml',
        'views/warranty_claim_views.xml',
        'wizard/warranty_out_wizard_view.xml',
        'report/report_warranty_certificate.xml',
        'report/report_warranty_claim_form.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
