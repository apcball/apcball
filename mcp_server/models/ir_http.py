# -*- coding: utf-8 -*-

import logging

from odoo import models
from odoo.http import request as http_request, root, db_filter

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_mcp_db(cls):
        """Resolve DB name from X-Odoo-DB header or db query param for MCP requests."""
        req = http_request.httprequest
        if not req.path.startswith('/mcp/'):
            return None
        db = req.headers.get('X-Odoo-DB') or req.args.get('db')
        if db:
            host = req.environ.get('HTTP_HOST', '')
            if db_filter([db], host=host):
                return db
        return None
