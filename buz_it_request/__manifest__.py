{
    "name": "IT Request Suite",
    "summary": "Manage IT Requests including Issues, Access, and Procurement",
    "description": """
    Complete IT Request Management Suite:
    - IT Request (Issues/Tickets) for reporting problems
    - IT Access Request for system access requests
    - IT Procurement Request for IT equipment procurement
    With dashboard, reporting, and approval workflows.
    """,
    "version": "17.0.1.0.0",
    "category": "IT Management/Helpdesk",
    "author": "apcball",
    "depends": [
        "base",
        "mail",
        "hr",
        "purchase",
        "stock",
    ],
    "data": [
        # Security
        "security/security.xml",
        "security/ir.model.access.csv",
        
        # Data
        "data/sequence.xml",
        "data/mail_activity.xml",
        "data/sla_data.xml",  # Moved before dashboard to ensure models are loaded
        "data/dashboard_data.xml",
        
        # Views
        "views/menu.xml",
        "views/it_ticket_issue_views.xml",
        "views/it_request_access_views.xml",
        "views/it_request_procurement_views.xml",
        "views/dashboard_views.xml",
        "views/report_templates.xml",
        
        # Reports
        "report/report_issue.xml",
        "report/report_access.xml",
        "report/report_procurement.xml",
    ],
    "assets": {
        'web.assets_backend': [
            # No specific assets needed initially
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}