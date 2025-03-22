{
    'name': 'BUZ Custom Quotation',
    'version': '1.0',
    'category': 'Sales',
    'summary': 'Custom Quotation Template',
    'description': """Custom Quotation form for BUZ""",
    'depends': [
        'sale_management',
        'sale_pdf_quote_builder',
    ],
    'data': [
        'data/sequence.xml',
        'security/ir.model.access.csv',
        'report/sale_report_templates.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': True,
}
    