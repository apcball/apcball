# -*- coding: utf-8 -*-
{
    "name": "buz MOG Expense: Petty Cash, Advance & Clearing (Odoo 17)",
    "summary": "Extend hr_expense to support petty cash boxes, employee/partner advances, and clearing flows.",
    "version": "17.0.1.0.0",
    "author": "Ball & Lime (มะนาว)",
    "website": "https://example.invalid",
    "license": "LGPL-3",
    "category": "Accounting/Expenses",
    "depends": ["hr_expense", "account", "contacts"],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "wizard/petty_cash_replenish_wizard_views.xml",
        "views/petty_cash_box_views.xml",
        "views/advance_request_views.xml",
        "views/clearing_views.xml",
        "views/hr_expense_sheet_views_inherit.xml",
        "wizard/advance_clear_wizard_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": True,
}
