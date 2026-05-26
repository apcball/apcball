# -*- coding: utf-8 -*-
{
    'name': 'MCP Server for Odoo',
    'version': '17.0.1.0.0',
    'category': 'Tools',
    'summary': 'Model Context Protocol server to expose Odoo tools to AI agents',
    'description': """
MCP Server for Odoo
===================
Exposes Odoo models as MCP tools for AI agent integration:
- Sale Order: search, read, create, write
- Product: search, read, create, write
- Stock Quant: search, read, inventory levels
    """,
    'author': 'AI-DEV-Module-Odoo17',
    'website': 'https://github.com/apcball/AI-DEV-Module-Odoo17',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'product',
        'stock',
        'account',
        'sales_team',
        'purchase',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/mcp_security.xml',
        'views/mcp_server_views.xml',
    ],
    'application': False,
    'installable': True,
    'auto_install': False,
}