# -*- coding: utf-8 -*-
"""
WSGI middleware that binds Odoo to the correct database for MCP requests.
This is loaded as a server-wide module via odoo.conf.
"""
import logging
import threading

import odoo
import odoo.http

_logger = logging.getLogger(__name__)

_original_call = None


def _patched_call(self, environ, start_response):
    """WSGI middleware: resolve DB from X-Odoo-DB header / db query param for /mcp/ requests."""
    path = environ.get('PATH_INFO', '')
    if path.startswith('/mcp/'):
        # Peek at X-Odoo-DB header or db query param
        db = None
        # Check header
        for key, val in environ.items():
            if key == 'HTTP_X_ODOO_DB':
                db = val
                break
        # Check query string
        if not db:
            qs = environ.get('QUERY_STRING', '')
            for part in qs.split('&'):
                if part.startswith('db='):
                    db = part[4:]
                    break
        if db:
            from odoo.http import db_filter
            host = environ.get('HTTP_HOST', '')
            if db_filter([db], host=host):
                # Inject into session
                environ.setdefault('HTTP_COOKIE', '')
                # We need to set session.db before _get_session_and_dbname runs
                # Store it in environ for the patched _get_session_and_dbname
                environ['mcp.forced_db'] = db

    return _original_call(self, environ, start_response)


def _patched_get_session_and_dbname(self):
    session, dbname = _orig_get_session(self)

    if not dbname:
        forced_db = self.httprequest.environ.get('mcp.forced_db')
        if forced_db:
            dbname = forced_db
            session.db = dbname

    return session, dbname


_orig_get_session = None


def post_load():
    global _original_call, _orig_get_session

    if _original_call:
        return  # Already patched

    _orig_get_session = odoo.http.Request._get_session_and_dbname
    _original_call = odoo.http.Application.__call__

    odoo.http.Request._get_session_and_dbname = _patched_get_session_and_dbname
    odoo.http.Application.__call__ = _patched_call

    _logger.info("MCP Server: WSGI middleware installed for X-Odoo-DB / db param support")
