{
    "name": "Buz Easy Transfer Plus",
    "version": "17.0.2.0.0",
    "category": "Inventory/Stock Management",
    "summary": "Enhanced Transfer Features for Odoo Inventory",
    "description": """
        This module adds enhanced functionality to Odoo's stock transfer features:
        - Select All Products button (only shown in transfers created from batches)
        - Clear Lines button to clear all transfer lines
        - Batch transfer creation functionality
        - Smart button in batch forms to view related internal transfers
        - Link between batch transfers and created internal transfers
        - Add to Batch Transfer button on receipts to create new batch transfers
    """,
    "author": "Ball (MOGEN)",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "stock_picking_batch",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_picking_views.xml",
        "views/stock_picking_batch_views.xml",
        "views/wizard_transfer_from_batch_views.xml",
        "views/add_to_batch_wizard_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}