# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class MrpStockRequestConfirmWizard(models.TransientModel):
    _name = "mrp.stock.request.confirm.wizard"
    _description = "Stock Request Confirmation Wizard"
    
    request_id = fields.Many2one(
        "mrp.stock.request",
        string="Stock Request",
        required=True,
        readonly=True,
    )
    location_id = fields.Many2one(
        related="request_id.location_id",
        string="Source Location",
        readonly=True,
    )
    location_dest_id = fields.Many2one(
        related="request_id.location_dest_id", 
        string="Destination Location",
        readonly=True,
    )
    line_ids = fields.One2many(
        related="request_id.line_ids",
        string="Request Lines",
        readonly=True,
    )
    notes = fields.Text(
        string="Confirmation Notes",
        readonly=True,
        compute="_compute_notes",
    )
    
    @api.depends("request_id", "location_id", "location_dest_id")
    def _compute_notes(self):
        for wizard in self:
            wizard.notes = _(
                "You are about to create an internal transfer from %s to %s.\n\n"
                "This will create stock moves for %d product line(s).\n\n"
                "Please confirm to proceed or cancel to abort."
            ) % (
                wizard.location_id.name if wizard.location_id else _("Not Set"),
                wizard.location_dest_id.name if wizard.location_dest_id else _("Not Set"),
                len(wizard.line_ids),
            )
    
    def action_confirm(self):
        """Confirm the stock request and create internal transfer."""
        self.ensure_one()
        # Call the new confirm method that handles the actual confirmation
        return self.request_id.action_confirm_with_validation()