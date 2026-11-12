{
    "name": "Bill / Invoice Payment Reference Report",
    "version": "17.0.1.0.0",
    "category": "Accounting/Reporting",
    "summary": "Vendor bills and customer invoices with the payment / receipt document numbers that settled them",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "views/bill_payment_ref_views.xml",
    ],
    "installable": True,
    "application": False,
}
