{
    'name': "Direct Print | Direct to Printer | Cloud Printing | Print Direct",
    'version': '17.0.1.0.0',
    'summary': "Direct Print Odoo App allows you to instantly print Odoo reports, invoices, and documents directly to any network or local printer using PrintNode integration. Streamline your printing workflows and eliminate manual downloads.",
    'description': """
        Direct Print Odoo Module streamlines Odoo document printing. This module uses PrintNode API to enable instant, direct printing of all Odoo reports, invoices, and more, eliminating downloads and enhancing efficiency. Compatible with various printers, it's ideal for manufacturing, retail, sales, and any Odoo user looking to automate their printing workflow.
    """,
    'category': 'Tools',
    "author": "Zehntech Technologies Inc.",
    "company": "Zehntech Technologies Inc.",
    "maintainer": "Zehntech Technologies Inc.",
    "contributor": "Zehntech Technologies Inc.",
    "website": "https://www.zehntech.com/",
    "support": "odoo-support@zehntech.com",
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/printnode_configuration_view.xml',
    ],
    'i18n': [
        'i18n/de.po',
        'i18n/es.po',
        'i18n/fr.po',
        'i18n/ja.po',
    ],
    "images": ['static/description/banner.gif'],
    'assets': {},
    'installable': True,
    'auto_install': False,
    'license': 'OPL-1',
}
