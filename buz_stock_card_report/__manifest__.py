{
    "name": "Stock Card Report",
    "version": "17.0.1.0.0",
    "category": "Inventory/Reports",
    "summary": "Export per-warehouse, per-product stock card (การ์ดสต๊อก) ledger to Excel",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "report_xlsx",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/stock_card_wizard_views.xml",
        "report/stock_card_report_action.xml",
    ],
    "installable": True,
    "application": False,
}
