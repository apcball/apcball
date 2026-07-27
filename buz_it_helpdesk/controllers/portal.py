from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools import html_sanitize
from odoo.addons.portal.controllers.portal import CustomerPortal
from werkzeug.exceptions import BadRequest


class HelpdeskPortal(CustomerPortal):
    @http.route("/my/helpdesk", type="http", auth="user", website=True)
    def portal_helpdesk(self, **kwargs):
        tickets = request.env["it.helpdesk.ticket"].search([("requester_id", "=", request.env.user.id)], order="create_date desc")
        return request.render("buz_it_helpdesk.portal_helpdesk_tickets", {"tickets": tickets})

    @http.route("/my/helpdesk/<int:ticket_id>", type="http", auth="user", website=True)
    def portal_helpdesk_detail(self, ticket_id, **kwargs):
        ticket = request.env["it.helpdesk.ticket"].search([("id", "=", ticket_id), ("requester_id", "=", request.env.user.id)], limit=1)
        if not ticket:
            return request.not_found()
        return request.render("buz_it_helpdesk.portal_helpdesk_ticket", {"ticket": ticket})

    @http.route("/my/helpdesk/new", type="http", auth="user", website=True, methods=["GET", "POST"])
    def portal_helpdesk_new(self, **post):
        if request.httprequest.method == "POST":
            ticket_model = request.env["it.helpdesk.ticket"]
            try:
                category_id, priority_id = ticket_model._validate_portal_selection(
                    post.get("category_id"), post.get("priority_id")
                )
            except ValidationError as error:
                raise BadRequest(str(error)) from error
            vals = {
                "subject": post.get("subject"),
                "description": html_sanitize(post.get("description") or ""),
                "requester_id": request.env.user.id,
                "source": "web",
                "category_id": category_id,
                "priority_id": priority_id,
            }
            ticket = ticket_model.create(vals)
            ticket.sudo()._add_uploaded_attachments(request.httprequest.files.getlist("attachments"))
            return request.redirect("/my/helpdesk")
        return request.render(
            "buz_it_helpdesk.portal_helpdesk_new",
            {
                "categories": request.env["it.helpdesk.category"].search([("company_id", "=", request.env.company.id), ("active", "=", True)]),
                "priorities": request.env["it.helpdesk.priority"].search([("company_id", "=", request.env.company.id), ("active", "=", True)]),
            },
        )

    @http.route("/my/helpdesk/<int:ticket_id>/confirm", type="http", auth="user", website=True, methods=["POST"])
    def portal_helpdesk_confirm(self, ticket_id, **post):
        ticket = request.env["it.helpdesk.ticket"].search([("id", "=", ticket_id), ("requester_id", "=", request.env.user.id)], limit=1)
        if not ticket:
            return request.not_found()
        ticket.action_confirm()
        return request.redirect("/my/helpdesk/%s" % ticket.id)

    @http.route("/my/helpdesk/<int:ticket_id>/reply", type="http", auth="user", website=True, methods=["POST"])
    def portal_helpdesk_reply(self, ticket_id, **post):
        ticket = request.env["it.helpdesk.ticket"].search([("id", "=", ticket_id), ("requester_id", "=", request.env.user.id)], limit=1)
        if not ticket:
            return request.not_found()
        body = (post.get("body") or "").strip()
        if body:
            ticket.action_portal_reply(body)
        ticket.sudo()._add_uploaded_attachments(request.httprequest.files.getlist("attachments"))
        return request.redirect("/my/helpdesk/%s" % ticket.id)