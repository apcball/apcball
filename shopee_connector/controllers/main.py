import werkzeug

from odoo import http
from odoo.http import request


class ShopeeCallbackController(http.Controller):
    @http.route(
        "/shopee/callback", type="http", auth="public", website=False, csrf=False
    )
    def shopee_callback(self, code=None, shop_id=None, **kwargs):
        """Shopee redirects here after the seller authorizes the app.
        Phase 1 assumption: single shop connection - stores the code/shop_id
        on the (first) active shopee.config record so the admin can click
        'Exchange Token' in the backend. Multi-shop support is Phase 2.
        """
        config = (
            request.env["shopee.config"]
            .sudo()
            .search([("active", "=", True)], limit=1)
        )
        if config and code:
            config.write({"temp_auth_code": code, "shop_id": shop_id})

        # Send the user back into the Odoo backend; they still need to
        # click "Exchange Token" manually on the Shopee Config record.
        return werkzeug.utils.redirect("/odoo", 302)
