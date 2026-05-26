# -*- coding: utf-8 -*-
"""
Server-wide module that patches Odoo's WSGI application
to resolve the correct database for /mcp/ requests.

Activated by adding 'mcp_db_resolver' to server_wide_modules
or simply by being importable when Odoo starts.
"""
import logging

import odoo.http

_logger = logging.getLogger(__name__)

_original_get_session = None


def _patched_get_session_and_dbname(self):
    """Resolve DB from X-Odoo-DB header or db query param for /mcp/ requests."""
    session, dbname = _original_get_session(self)

    if not dbname:
        path = self.httprequest.path
        if path.startswith('/mcp/'):
            db = self.httprequest.headers.get('X-Odoo-DB') or self.httprequest.args.get('db')
            if db:
                from odoo.http import db_filter
                host = self.httprequest.environ.get('HTTP_HOST', '')
                if db_filter([db], host=host):
                    dbname = db
                    session.db = dbname

    return session, dbname


# Apply patch at import time (runs when Odoo loads this module)
_original_get_session = odoo.http.Request._get_session_and_dbname
odoo.http.Request._get_session_and_dbname = _patched_get_session_and_dbname
_logger.info("MCP DB Resolver: patched Request._get_session_and_dbname")
