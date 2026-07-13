import base64

from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


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
            vals = {"subject": post.get("subject"), "description": post.get("description"), "requester_id": request.env.user.id, "source": "web", "category_id": int(post["category_id"]), "priority_id": int(post["priority_id"])}
            ticket = request.env["it.helpdesk.ticket"].create(vals)
            self._attach_uploads(ticket, request.httprequest.files.getlist("attachments"))
            return request.redirect("/my/helpdesk")
        return request.render("buz_it_helpdesk.portal_helpdesk_new", {"categories": request.env["it.helpdesk.category"].search([]), "priorities": request.env["it.helpdesk.priority"].search([])})

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
            ticket.message_post(body=body, message_type="comment", subtype_xmlid="mail.mt_comment")
        self._attach_uploads(ticket, request.httprequest.files.getlist("attachments"))
        return request.redirect("/my/helpdesk/%s" % ticket.id)

    @staticmethod
    def _attach_uploads(ticket, uploads):
        Attachment = request.env["ir.attachment"]
        for upload in uploads:
            if upload and upload.filename:
                Attachment.create({"name": upload.filename, "datas": base64.b64encode(upload.read()), "res_model": ticket._name, "res_id": ticket.id, "type": "binary"})
