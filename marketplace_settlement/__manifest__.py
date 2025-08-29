{
    "name": "Marketplace Settlement (Shopee/Lazada)",
    "summary": "Wizard to group many customer invoices into a single receivable to marketplace (e.g., Shopee)",
    "version": "17.0.1.0.0",
    "author": "Ball + Manow",
    "category": "Accounting/Localizations",
    "website": "https://example.com",
    "license": "LGPL-3",
    "depends": ["account", "sale"],
    "data": [
        "security/ir.model.access.csv",
    "views/marketplace_settlement_wizard_views.xml",
    "views/profile_views.xml",
        "views/sale_order_view_inherit.xml",
        "views/account_move_view_inherit.xml",
    ],
    "demo": [
        "data/demo_data.xml",
    ],
    # Custom JS assets removed temporarily to avoid webclient break while debugging
    "installable": True,
    "application": False,
}
