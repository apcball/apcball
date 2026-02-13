{
    "name": "BUZ Planning (Gantt)",
    "version": "17.0.1.0.0",
    "category": "Planning",
    "summary": "Native OWL Gantt Planning for Odoo 17 Community",
    "description": """
        Planning module with custom OWL Gantt view.
        Supports planning slots linked to project tasks and MRP work orders.
        Features: drag & drop, resize, group by employee/workcenter, zoom levels.
    """,
    "author": "BUZ",
    "license": "LGPL-3",
    "depends": [
        "base",
        "hr",
        "project",
        "mrp",
        "web",
    ],
    "data": [
        "security/mog_planning_groups.xml",
        "security/ir.model.access.csv",
        "security/mog_planning_rules.xml",
        "views/planning_slot_views.xml",
        "views/planning_slot_calendar.xml",
        "views/planning_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "buz_planning/static/src/views/mog_gantt/mog_gantt.scss",
            "buz_planning/static/src/views/mog_gantt/mog_gantt_arch_parser.js",
            "buz_planning/static/src/views/mog_gantt/mog_gantt_model.js",
            "buz_planning/static/src/views/mog_gantt/mog_gantt_renderer.js",
            "buz_planning/static/src/views/mog_gantt/mog_gantt_controller.js",
            "buz_planning/static/src/views/mog_gantt/mog_gantt_view.js",
            "buz_planning/static/src/views/mog_gantt/mog_gantt_templates.xml",
        ],
    },
    "installable": True,
    "application": True,
}
