{
    "name": "PO Receipt Report (Foreign / Domestic)",
    "version": "17.0.1.0.0",
    "category": "Inventory/Reporting",
    "summary": "Excel report of done receipts from PO, split foreign / domestic, with landed cost columns",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "purchase",
        "stock_picking_batch",
        "buz_purchase_receipt_exchange_rate",
        "buz_landed_cost_report",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/po_receipt_report_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
