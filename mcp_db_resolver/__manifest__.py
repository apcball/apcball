# -*- coding: utf-8 -*-
{
    'name': 'MCP DB Resolver',
    'version': '17.0.1.0.0',
    'category': 'Tools',
    'summary': 'WSGI middleware to resolve Odoo database for MCP requests',
    'description': """
    Resolves the correct Odoo database for /mcp/ requests using
    X-Odoo-DB header or db query parameter in multi-database setups.
    Must be listed in server_wide_modules.
    """,
    'author': 'AI-DEV-Module-Odoo17',
    'license': 'LGPL-3',
    'depends': [],
    'installable': True,
    'auto_install': False,
}
