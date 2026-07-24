{
    "name": "Mogen Smart S&OP Forecast",
    "summary": "Advanced statistical forecasting foundation for Smart S&OP",
    "version": "17.0.1.0.0",
    "category": "Operations/Planning",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": ["mogen_sop_core", "mogen_sop_demand", "sale_management", "stock"],
    "data": [
        "security/forecast_security.xml",
        "security/ir.model.access.csv",
        "data/forecast_model_data.xml",
        "views/forecast_views.xml",
        "views/forecast_menu.xml",
    ],
    "application": False,
    "installable": True,
}
