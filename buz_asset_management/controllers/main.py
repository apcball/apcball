# -*- coding: utf-8 -*-
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request


class BuzAssetQR(http.Controller):

    @http.route('/buz_asset/qr/<string:token>', type='http', auth='user', website=False)
    def asset_qr(self, token, **kwargs):
        """Open the asset behind a QR label. Login is required and record rules
        apply, so the token alone never exposes anything. An unknown token and
        an asset the user may not read look identical (404)."""
        url = request.env['buz.asset']._qr_target_url(token)
        if not url:
            raise NotFound()
        return request.redirect(url)
