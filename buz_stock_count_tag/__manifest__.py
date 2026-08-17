{
    "name": "Stock Count TAG Generator",
    "version": "17.0.1.0.0",
    "category": "Inventory",
    "summary": "Import product list, generate print-ready stock-count TAG forms as one Excel workbook",
    "description": """
Stock Count TAG Generator
==========================
Import a product list from Excel, review/edit it in Odoo, then generate one
Excel workbook containing all TAG forms (ต้นฉบับ + สำเนา) as print-ready pages
using the company's existing TAG template. 1 product = 1 form = 1 printed page.
    """,
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": [
        "base",
        "stock",
        "mail",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "wizard/stock_count_tag_import_wizard_views.xml",
        "views/stock_count_tag_views.xml",
        "views/stock_count_tag_menu.xml",
    ],
    "external_dependencies": {
        "python": ["openpyxl"],
    },
    "installable": True,
    "application": False,
}
