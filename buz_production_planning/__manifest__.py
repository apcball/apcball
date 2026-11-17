{
    'name': 'Production Planning (Demand → MRP → Schedule)',
    'version': '17.0.1.1.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Demand-driven make/buy suggestions and finite-capacity workorder scheduling',
    'author': 'Mogen Co.',
    'license': 'LGPL-3',
    'depends': [
        'mrp', 'purchase_stock', 'purchase_requisition', 'purchase_requisition_stock',
        'sale_stock', 'stock', 'mail',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/ir_config_parameter.xml',
        'views/plan_product_param_views.xml',
        'views/plan_create_documents_views.xml',
        'views/plan_run_views.xml',
        'views/plan_suggestion_views.xml',
        'views/plan_demand_line_views.xml',
        'views/plan_schedule_line_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_production_planning/static/src/gantt/gantt_action.js',
            'buz_production_planning/static/src/gantt/gantt_action.xml',
            'buz_production_planning/static/src/gantt/gantt.scss',
        ],
    },
    'application': True,
}
