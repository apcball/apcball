from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BuzReservationExtendWizard(models.TransientModel):
    _name = "buz.reservation.extend.wizard"
    _description = "Extend Reservation Expiry Wizard"

    reservation_id = fields.Many2one(
        "buz.stock.reservation", required=True, readonly=True
    )
    current_expiry_date = fields.Datetime(
        related="reservation_id.expiry_date", string="Current Expiry"
    )
    new_expiry_date = fields.Datetime(
        string="New Expiry Date",
        required=True,
        default=lambda self: self._default_new_expiry(),
    )
    note = fields.Char(string="Note")

    @api.model
    def _default_new_expiry(self):
        reservation = self.env["buz.stock.reservation"].browse(
            self.env.context.get("default_reservation_id")
        )
        base = reservation.expiry_date or fields.Datetime.now()
        return base + timedelta(days=7)

    def action_extend(self):
        self.ensure_one()
        reservation = self.reservation_id
        if self.new_expiry_date <= fields.Datetime.now():
            raise UserError(_("New expiry date must be in the future."))
        old_expiry = reservation.expiry_date
        vals = {"expiry_date": self.new_expiry_date}
        if reservation.state == "expired":
            vals["state"] = "reserved"
        reservation.write(vals)
        reservation._invalidate_product_availability()
        body = _(
            "Expiry date extended from %(old)s to %(new)s.",
            old=fields.Datetime.to_string(old_expiry),
            new=fields.Datetime.to_string(self.new_expiry_date),
        )
        if self.note:
            body += " %s" % self.note
        reservation.message_post(body=body)
        return {"type": "ir.actions.act_window_close"}
