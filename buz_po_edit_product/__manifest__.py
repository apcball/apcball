{
    "name": "Purchase Order Line - Edit Product After Return",
    "version": "17.0.1.0.0",
    "summary": "Allow correcting product code on a confirmed PO line after stock has been fully returned, with no accounting impact",
    "category": "Purchases",
    "author": "Mogen Co.",
    "depends": ["purchase", "stock_account"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/purchase_order_views.xml",
        "wizard/po_line_change_product_views.xml",
    ],
    "installable": True,
    "license": "LGPL-3",
}
