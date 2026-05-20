{
    "name": "Sale Order Line Credit Note",
    "version": "17.0.1.0.0",
    "summary": "Create customer credit notes from Sale Order invoice lines via wizard",
    "category": "Sales",
    "author": "Custom",
    "website": "",
    "license": "LGPL-3",
    "depends": [
        "sale_management",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/sale_order_views.xml",
        "views/sale_order_credit_note_wizard_views.xml",
    ],
    "application": False,
    "installable": True,
}
