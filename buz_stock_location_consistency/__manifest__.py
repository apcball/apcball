{
    "name": "BUZ Stock Location Consistency",
    "version": "17.0.1.3.0",
    "category": "Inventory/Inventory",
    "summary": "Keep stock move line source consistent with the move header; "
               "report existing mismatches",
    "author": "Mogen Co.",
    "license": "LGPL-3",
    "depends": ["stock", "stock_fifo_by_location"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_move_line_mismatch_views.xml",
    ],
    "installable": True,
    "application": False,
}
