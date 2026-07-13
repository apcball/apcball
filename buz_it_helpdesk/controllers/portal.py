import base64

from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class HelpdeskPortal(CustomerPortal):
    @http.route("/my/helpdesk", type="http", auth="user", website=True)
    def portal_helpdesk(self, **kwargs):
        tickets = request.env["it.helpdesk.ticket"].sudo().search([("requester_id", "=", request.env.user.id)], order="create_date desc")
        return request.render("buz_it_helpdesk.portal_helpdesk_tickets", {"tickets": tickets})

    @http.route("/my/helpdesk/new", type="http", auth="user", website=True, methods=["GET", "POST"])
    def portal_helpdesk_new(self, **post):
        if request.httprequest.method == "POST":
            vals = {"subject": post.get("subject"), "description": post.get("description"), "requester_id": request.env.user.id, "source": "web", "category_id": int(post["category_id"]), "priority_id": int(post["priority_id"])}
            ticket = request.env["it.helpdesk.ticket"].sudo().create(vals)
            return request.redirect("/my/helpdesk")
        return request.render("buz_it_helpdesk.portal_helpdesk_new", {"categories": request.env["it.helpdesk.category"].sudo().search([]), "priorities": request.env["it.helpdesk.priority"].sudo().search([])})
