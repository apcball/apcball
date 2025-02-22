# -*- coding: utf-8 -*-
{
    'name' : 'buz Approvals Teams',
    'version' : '17.0.1.0.0',
    'summary': 'This module enables multi-level approval processes across various models in Odoo. It allows users to set up custom approvers and create teams to manage and streamline approvals.',
    'sequence': -100,
    'description': """This module provides multi-level approval functionality for different models, allowing users to set approvers and create teams for approval processes.""",
    'author': 'KoderXpert Technologies LLP',
    'company': 'KoderXpert Technologies LLP',
    'maintainer': 'KoderXpert Technologies LLP',
    'website': 'https://koderxpert.com',
    'category': 'Productivity',
    'images' : [],
    'depends' : ['base','sale','purchase','account',],
    'data': [
    
        'security/ir.model.access.csv',
        'data/approval_model_data.xml',
        'views/team_view.xml',
        'views/approval_view.xml',
      
        ],
    'demo': [],
    'installable':True,
    'application':True,
    'auto_install':False,
    'license': 'LGPL-3',

    'images':['static/description/gif.gif'],
}
