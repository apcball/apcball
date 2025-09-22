# -*- coding: utf-8 -*-
{
    "name": "buz Account WHT Installment (TH)",
    "summary": "Partial payments on vendor bills with withholding tax and VAT calculation (Thailand)",
    "version": "17.0.1.1.0",
    "category": "Accounting",
    "author": "apcball + Manow",
    "website": "https://example.local",
    "license": "LGPL-3",
    "depends": ["account", "l10n_th_account_tax"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/account_move_views.xml",
        "views/installment_wht_wizard_views.xml",
        "data/defaults.xml",
    ],
    "installable": True,
    "application": False,
}
