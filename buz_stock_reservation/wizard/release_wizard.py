from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BuzReservationReleaseWizard(models.TransientModel):
    _name = "buz.reservation.release.wizard"
    _description = "Release Reservation Wizard"

    reservation_id = fields.Many2one(
        "buz.stock.reservation", required=True, readonly=True
    )
    release_reason_id = fields.Many2one(
        "buz.reservation.release.reason", string="Reason", required=True
    )
    note = fields.Char(string="Note")
    line_ids = fields.One2many(
        "buz.reservation.release.wizard.line", "wizard_id", string="Lines"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        reservation = self.env["buz.stock.reservation"].browse(
            res.get("reservation_id") or self.env.context.get("default_reservation_id")
        )
        if reservation and "line_ids" in fields_list:
            res["line_ids"] = [
                fields.Command.create(
                    {
                        "reservation_line_id": line.id,
                        "release_qty": line.remaining_qty,
                    }
                )
                for line in reservation.line_ids
                if line.remaining_qty > 0
            ]
        return res

    def action_release(self):
        self.ensure_one()
        lines = self.line_ids.filtered("release_qty")
        if not lines:
            raise UserError(_("Enter a quantity to release on at least one line."))
        for wline in lines:
            line = wline.reservation_line_id
            if wline.release_qty < 0 or wline.release_qty > line.remaining_qty:
                raise UserError(
                    _(
                        "Release quantity for '%(product)s' must be between 0 "
                        "and %(remaining).2f.",
                        product=line.product_id.display_name,
                        remaining=line.remaining_qty,
                    )
                )
            line.released_qty += wline.release_qty
        self.reservation_id._apply_release(
            reason=self.release_reason_id, note=self.note
        )
        return {"type": "ir.actions.act_window_close"}


class BuzReservationReleaseWizardLine(models.TransientModel):
    _name = "buz.reservation.release.wizard.line"
    _description = "Release Reservation Wizard Line"

    wizard_id = fields.Many2one(
        "buz.reservation.release.wizard", required=True, ondelete="cascade"
    )
    reservation_line_id = fields.Many2one(
        "buz.stock.reservation.line", required=True, readonly=True
    )
    product_id = fields.Many2one(
        related="reservation_line_id.product_id", readonly=True
    )
    remaining_qty = fields.Float(
        related="reservation_line_id.remaining_qty", readonly=True
    )
    release_qty = fields.Float(string="Release Qty")
