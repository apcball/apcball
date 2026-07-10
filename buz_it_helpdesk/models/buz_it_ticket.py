# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class BuzItTicket(models.Model):
    _name = "buz.it.ticket"
    _description = "IT Helpdesk Ticket"
    _order = "priority desc, id desc"
    _rec_name = "ticket_no"

    ticket_no = fields.Char(
        string="Ticket No.",
        default="New",
        readonly=True,
        copy=False,
        index=True,
    )
    name = fields.Char(string="Subject", required=True)
    requester_id = fields.Many2one(
        "res.users",
        string="Requester",
        default=lambda self: self.env.user,
        required=True,
        ondelete="restrict",
    )
    requester_name = fields.Char(
        string="Requester Name",
        compute="_compute_requester_info",
        store=True,
        readonly=True,
    )
    requester_email = fields.Char(
        string="Requester Email",
        compute="_compute_requester_info",
        store=True,
        readonly=True,
    )
    requester_phone = fields.Char(
        string="Requester Phone",
        compute="_compute_requester_info",
        store=True,
        readonly=True,
    )
    contact_channel = fields.Selection(
        [
            ("phone", "Phone"),
            ("email", "Email"),
            ("line", "LINE"),
            ("chat", "Chat"),
            ("other", "Other"),
        ],
        string="Contact Channel",
        required=True,
        default="phone",
    )
    ticket_category = fields.Selection(
        [
            ("hardware", "Hardware"),
            ("software", "Software"),
            ("network", "Network"),
            ("printer", "Printer"),
            ("system", "System / Access"),
            ("other", "Other"),
        ],
        string="Ticket Category",
        required=True,
        default="hardware",
    )
    symptom = fields.Text(string="Symptom", required=True)
    assigned_to_id = fields.Many2one(
        "res.users",
        string="Assigned To",
        default=lambda self: self.env.user,
        ondelete="set null",
    )
    priority = fields.Selection(
        [
            ("0", "Low"),
            ("1", "Normal"),
            ("2", "High"),
            ("3", "Urgent"),
        ],
        string="Priority",
        default="1",
        required=True,
    )
    requested_timeframe = fields.Char(
        string="Requested Timeframe",
        help="Timeframe requested by the ticket reporter.",
        required=True,
    )
    opened_date = fields.Date(
        string="Opened Date",
        default=fields.Date.context_today,
        readonly=True,
        copy=False,
    )
    received_date = fields.Date(
        string="Received Date",
        readonly=True,
        copy=False,
    )
    closed_date = fields.Date(
        string="Closed Date",
        readonly=True,
        copy=False,
    )
    stage = fields.Selection(
        [
            ("new", "New"),
            ("in_progress", "In Progress"),
            ("resolved", "Resolved"),
            ("closed", "Closed"),
        ],
        string="Stage",
        default="new",
        required=True,
    )
    description = fields.Text(string="Description")

    _sql_constraints = [
        ("ticket_no_unique", "unique(ticket_no)", "Ticket number must be unique."),
    ]

    @api.depends(
        "requester_id",
        "requester_id.name",
        "requester_id.partner_id.email",
        "requester_id.partner_id.phone",
        "requester_id.partner_id.mobile",
    )
    def _compute_requester_info(self):
        for rec in self:
            user = rec.requester_id
            partner = user.partner_id if user else False
            rec.requester_name = user.name if user else False
            rec.requester_email = partner.email if partner else False
            rec.requester_phone = (partner.mobile or partner.phone) if partner else False

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        today = fields.Date.context_today(self)
        for vals in vals_list:
            if vals.get("ticket_no", "New") == "New":
                vals["ticket_no"] = sequence.next_by_code("buz.it.ticket") or _("New")
            vals.setdefault("requester_id", self.env.user.id)
            vals.setdefault("opened_date", today)
        return super().create(vals_list)

    def write(self, vals):
        today = fields.Date.context_today(self)
        if vals.get("assigned_to_id") and not vals.get("received_date"):
            vals.setdefault("received_date", today)
        if vals.get("stage") in ("in_progress", "resolved", "closed") and not vals.get(
            "received_date"
        ):
            vals.setdefault("received_date", today)
        if vals.get("stage") == "closed" and not vals.get("closed_date"):
            vals.setdefault("closed_date", today)
        return super().write(vals)
