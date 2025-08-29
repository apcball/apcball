# Copyright 2019 Ecosoft Co., Ltd (https://ecosoft.co.th)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

{
    "name": "Thai Localization - VAT and Withholding Tax Reports",
    "version": "17.0.1.0.0",
    "author": "Ecosoft, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-thailand",
    "license": "AGPL-3",
    "category": "Accounting/Localizations",
    "depends": [
        "base",
        "account",
        "date_range",
        "report_xlsx_helper",
        "l10n_th_base_utils",
        "l10n_th_partner", 
        "l10n_th_account_tax",
    ],
    "data": [
        # Load security first
        "security/ir.model.access.csv",
        # Load core data
        "data/paper_format.xml",
        "data/report_data.xml",
        # Load views
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
        # Load wizards
        "wizard/tax_report_wizard_view.xml",
        "wizard/withholding_tax_report_wizard_view.xml",
        # Load report templates
        "reports/templates/tax_report.xml",
        "reports/templates/tax_report_rd.xml",
        "reports/templates/wht_report.xml",
        "reports/templates/wht_report_rd_pnd1.xml",
        "reports/templates/wht_report_rd_pnd1a.xml",
        "reports/templates/wht_report_rd_pnd2.xml",
        "reports/templates/wht_report_rd_pnd3.xml",
        "reports/templates/wht_report_rd_pnd53.xml",
        "reports/templates/wht_report_rd.xml",
        "reports/templates/wht_report_text.xml",
        # Load menus last
        "views/account_menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "l10n_th_account_tax_report/static/src/scss/style_report.scss",
        ],
        "web.report_assets_common": [
            "l10n_th_account_tax_report/static/src/scss/style_report.scss",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
    "sequence": 100,
    "development_status": "Beta",
    "maintainers": ["kittiu", "Saran440"],
    "external_dependencies": {
        "python": ["xlsxwriter"],
    },
    "pre_init_hook": "pre_init_hook",
    "post_init_hook": "post_init_hook", 
    "uninstall_hook": "uninstall_hook",
}
