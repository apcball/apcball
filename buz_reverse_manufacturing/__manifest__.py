# Part of buz addons for Mogen Co. See LICENSE file.
{
    "name": "Buz Reverse Manufacturing",
    "version": "17.0.1.0.0",
    "category": "Manufacturing",
    "summary": "Disassembly with work orders, labor cost and cost allocation "
               "built on Manufacturing Orders (not Unbuild)",
    "description": """
Reverse Manufacturing
=====================
Disassemble a finished product through standard Manufacturing Orders so the
full manufacturing framework is reused: work orders, work centers, routing,
tablet view, employee time tracking, labor cost, OEE.

Flow: Finished Product -> Work Orders -> Recovered Components.

The input cost (finished product valuation + labor + operations + extra cost)
is distributed across the recovered components by a configurable allocation
method (BOM cost ratio, percentage, quantity, weight or manual amount).
""",
    "author": "Mogen Co.",
    "website": "https://www.mogen.co.th",
    "license": "LGPL-3",
    "depends": [
        "mrp",
        "mrp_account",
        # mrp_workorder (Enterprise) intentionally NOT a hard dependency:
        # DEV runs community addons only. The module never references
        # mrp_workorder models; tablet view / time tracking light up
        # automatically on databases where mrp_workorder is installed.
        "stock",
        "stock_account",
        "hr",
        "mail",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/mrp_bom_views.xml",
        "views/reverse_recovery_line_views.xml",
        "views/mrp_production_views.xml",
        "report/report_paperformat.xml",
        "report/report_reverse_manufacturing.xml",
        "report/report_action.xml",
        "views/menu.xml",
    ],
    "demo": [
        "demo/product_demo.xml",
        "demo/mrp_bom_demo.xml",
    ],
    "installable": True,
    "application": False,
}
