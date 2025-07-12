# -*- coding: utf-8 -*-
{
    'name': 'buz Project Job Costing Management for Construction',
    'version': '17.0.1.0.0',
    'category': 'Project',
    'summary': 'Project Job Costing (Contracting) and Job Cost Sheet for Construction Management',
    'description': """
Project Job Costing Management for Construction
===============================================

This module provides comprehensive job costing management for construction projects including:

Main Features:
--------------
* Job Cost Sheet management with Material, Labour, and Overhead costing
* Project and Contract management with job orders/work orders
* Material requisition and BOQ (Bill of Quantities) management
* Subcontractor management
* Integration with Purchase Orders, Vendor Bills, and Timesheets
* Cost center tracking and analytics
* Comprehensive reporting for projects, job orders, and cost sheets
* Material planning and consumption tracking
* Real-time actual vs planned cost comparison

Modules Included:
-----------------
* Job Cost Sheets with three-tab structure (Materials, Labour, Overheads)
* Project/Contract management
* Job Orders/Work Orders (based on project tasks)
* Material requisition system
* Subcontractor management
* Job types and stages configuration
* Integration with accounting and timesheet modules

Key Benefits:
-------------
* Complete cost control for construction projects
* Real-time tracking of planned vs actual costs
* Streamlined material requisition process
* Integration with existing Odoo modules (Project, Purchase, Timesheet, Accounting)
* Detailed reporting and analytics
* Multi-level approval workflows
    """,
    'author': 'Apichart Pangsalung',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'project',
        'purchase',
        'stock',
        'hr_timesheet',
        'account',
        'analytic',
        'hr',
        'mail',
        'portal',
    ],
    'data': [
        # Security
        'security/job_costing_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/job_sequence.xml',
        'data/job_stages_data.xml',
        'data/boq_sequence.xml',
        
        # Views
        'views/job_type_views.xml',
        'views/job_stage_views.xml',
        'views/job_cost_sheet_views.xml',
        'views/project_views.xml',
        'views/job_order_views.xml',
        'views/material_requisition_views.xml',
        'views/boq_views.xml',
        'views/subcontractor_views.xml',
        'views/job_note_views.xml',
        'views/purchase_order_views.xml',
        'views/account_move_views.xml',
        'views/hr_timesheet_views.xml',
        'views/job_costing_menu.xml',
        
        # Reports
        'reports/job_cost_sheet_report.xml',
        'reports/project_report.xml',
        'reports/job_order_report.xml',
        'reports/material_requisition_report.xml',
        'reports/boq_report.xml',
    ],
    'demo': [
        'demo/job_costing_demo.xml',
        'demo/boq_demo.xml',
    ],
    'qweb': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
}
