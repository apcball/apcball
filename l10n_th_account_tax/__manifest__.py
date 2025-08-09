# Copyright 2019 Ecosoft Co., Ltd (http://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

{
    "name": "Thai Localization - VAT and Withholding Tax",
    "version": "17.0.1.1.1",
    "author": "Ecosoft, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "website": "https://github.com/OCA/l10n-thailand",
    "category": "Localization / Accounting",
    "depends": ["account", "base"],
    "data": [
        # Core Data - WHT Tax System 
        "data/pit_rate_data.xml",
        "data/withholding_tax_type_income_data.xml",
        # "data/wht_tax_system.xml",  # Temporarily disabled - has account creation issues
        
        # Security
        "security/account_security.xml",
        "security/ir.model.access.csv",
        
        # Wizards - Enhanced
        "wizard/wht_manual_create_wizard_view.xml",
        "wizard/account_payment_register_views.xml",
        "wizard/account_move_reversal_view.xml",
        # "wizard/wht_cert_generator_views.xml",  # Temporarily disabled for debugging
        # "wizard/wht_setup_wizard_views.xml",  # Temporarily disabled for debugging
        
        # Views - Core and Enhanced
        "views/res_config_settings_views.xml",
        "views/account_view.xml",
        "views/account_tax_view.xml",
        "views/account_move_view.xml",
        "views/withholding_tax_cert.xml",
        "views/account_withholding_tax.xml",
        "views/withholding_tax_code_income.xml",
        "views/account_withholding_move.xml",
        "views/product_view.xml",
        "views/account_payment_view.xml",
        "views/personal_income_tax_view.xml",
        "views/res_partner_view.xml",
        "views/account_menu.xml",
        "views/hr_expense_sheet_tax_invoice_view.xml",
        "views/account_withholding_tax_odoo17.xml",
        # "views/wht_tax_system_views.xml",  # Temporarily disabled - field dependency issues
    ],
    "depends": ["account", "base", "hr_expense", "product"],
    "test": [
        "tests/test_missing_record_handling.py",
    ],
    "installable": True,
    "development_status": "Beta",
    "maintainers": ["kittiu"],
    # "post_init_hook": "post_init_hook",  # Temporarily disabled for debugging
}
