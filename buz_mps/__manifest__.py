{
    "name": "BUZ Master Production Schedule",
    "version": "17.0.1.0.0",
    "category": "Manufacturing",
    "summary": "Master Production Schedule with MO/PO generation and Planning integration",
    "description": """
        Master Production Schedule (MPS) for Odoo 17 Community.
        - Forecast-driven replenishment planning
        - Automatic MO generation from MPS
        - Automatic planning slot creation for workorders
        - Full integration: MPS → MO → Workorder → Planning Slot → Gantt
    """,
    "author": "BUZ",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mrp",
        "purchase",
        "stock",
        "buz_planning",
    ],
    "data": [
        "security/mps_groups.xml",
        "security/ir.model.access.csv",
        "security/mps_rules.xml",
        "views/mps_plan_views.xml",
        "views/mps_plan_line_views.xml",
        "views/mps_menus.xml",
    ],
    "installable": True,
    "application": True,
}
