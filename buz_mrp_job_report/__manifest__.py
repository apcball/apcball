{
    "name": "MRP Job Close Report (Excel)",
    "version": "17.0.1.1.0",
    "category": "Manufacturing/Reports",
    "summary": "Excel job ledger: MO header, issued materials, output, returns, employee time",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": ["mrp", "stock", "hr", "buz_mrp_stock_request"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/mrp_job_report_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
