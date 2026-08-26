{
    "name": "BUZ Account Credit Note Deferred Reconcile",
    "version": "17.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Prevent automatic reconciliation between invoices and credit notes",
    "author": "Mogen Co.",
    "license": "LGPL-3",
    "depends": [
        "account",
    ],
    "data": [
        "security/security.xml",
        "views/res_config_settings_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}
