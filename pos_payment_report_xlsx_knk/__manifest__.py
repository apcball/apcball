# -*- coding: utf-8 -*-
# Powered by Kanak Infosystems LLP.
# © 2020 Kanak Infosystems LLP. (<https://www.kanakinfosystems.com>).

{
    'name': 'buz POS Payment Report (XLSX)',
    'version': '17.0.1.0',
    'description': 'Generate an XLSX report for POS payments based on selected payment methods.',
    'summary': 'POS Payment Method Report | Odoo POS Payment Report | POS Payment XLSX Export | POS Payment Method Report | Odoo POS Sales Report | Generate POS Payment Report Odoo | POS Report by Payment Type Odoo | POS XLSX Report Generator Odoo', 'category': 'Point of Sale',
    'license': 'OPL-1',
    'author': 'Kanak Infosystems LLP.',
    'website': 'https://www.kanakinfosystem.com',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/pos_payment_report_wizard.xml',
    ],
    'images': ['static/description/banner.png'],
    "installable": True
}
