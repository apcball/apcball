from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ReservationReleaseWizard(models.TransientModel):
    """Wizard for mass-releasing stock reservations."""

    _name = "reservation.release.wizard"
    _description = "Reservation Release Wizard"

    # ── Wizard Fields ────────────────────────────────────────────

    reservation_ids = fields.Many2many(
        comodel_name="stock.reservation",
        string="Reservations to Release",
        domain=[("state", "not in", ("released", "cancel", "delivered"))],
        required=True,
    )
    release_date = fields.Date(
        string="Release Date",
        required=True,
        default=fields.Date.context_today,
    )
    reason = fields.Selection(
        selection=[
            ("customer_cancellation", "Customer Cancellation"),
            ("expired", "Expired Reservation"),
            ("product_change", "Product Change"),
            ("stock_adjustment", "Stock Adjustment"),
            ("manual", "Manual Release"),
            ("other", "Other"),
        ],
        string="Release Reason",
        required=True,
        default="manual",
    )
    reason_note = fields.Text(string="Additional Notes")
    auto_create_credit_note = fields.Boolean(
        string="Create Credit Note",
        default=False,
        help="If the reservation is linked to a delivered sale order, "
        "create a draft credit note for the released quantities.",
    )
    notify_customer = fields.Boolean(
        string="Notify Customer",
        default=True,
        help="Send email notification to customer about the release.",
    )
    confirmed = fields.Boolean(
        string="Confirmed",
        default=False,
    )

    line_ids = fields.One2many(
        comodel_name="reservation.release.wizard.line",
        inverse_name="wizard_id",
        string="Release Lines",
        readonly=True,
    )

    # ── Counts (display only) ───────────────────────────────────
    reservation_count = fields.Integer(
        string="Reservation Count",
        compute="_compute_counts",
    )
    total_to_release = fields.Float(
        string="Total Qty to Release",
        compute="_compute_counts",
    )

    @api.depends("reservation_ids")
    def _compute_counts(self):
        for wiz in self:
            wiz.reservation_count = len(wiz.reservation_ids)
            wiz.total_to_release = sum(wiz.reservation_ids.mapped("total_reserve_qty"))

    # ── Populate Lines ──────────────────────────────────────────

    @api.onchange("reservation_ids")
    def _onchange_reservation_ids(self):
        """Populate wizard lines from selected reservations."""
        if not self.reservation_ids:
            self.line_ids = [(5, 0, 0)]
            return

        lines_data = []
        for res in self.reservation_ids:
            for line in res.line_ids:
                lines_data.append(
                    (
                        0,
                        0,
                        {
                            "reservation_id": res.id,
                            "product_id": line.product_id.id,
                            "reserve_qty": line.reserve_qty,
                            "allocated_qty": line.allocated_qty,
                            "released_qty": line.released_qty,
                            "to_release": True,
                        },
                    )
                )
        self.line_ids = [(5, 0, 0)] + lines_data

    # ── Action Methods ──────────────────────────────────────────

    def action_release(self):
        """Execute the mass release."""
        self.ensure_one()

        if not self.confirmed:
            return {
                "type": "ir.actions.act_window",
                "res_model": "reservation.release.wizard",
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_confirmed": True,
                    "default_reason": self.reason,
                    "default_reason_note": self.reason_note,
                    "default_notify_customer": self.notify_customer,
                },
            }

        for reservation in self.reservation_ids:
            # Prepare release note
            note_parts = [f"Released: {dict(self._fields['reason'].selection).get(self.reason, self.reason)}"]
            if self.reason_note:
                note_parts.append(self.reason_note)

            reservation.write({
                "note": (reservation.note or "") + "<br/>" + "<br/>".join(note_parts),
            })
            reservation.action_release()

            # Notify customer if requested
            if self.notify_customer and reservation.customer_id.email:
                reservation.message_post_with_template(
                    "stock_reservation_management.mail_template_reservation_expired",
                    email_layout_xmlid="mail.mail_notification_light",
                )

        return {
            "type": "ir.actions.act_window_close",
        }

    def action_draft(self):
        """Return reservations to draft before release."""
        for reservation in self.reservation_ids:
            if reservation.state in ("expired", "released", "cancel", "delivered"):
                raise UserError(
                    _("Reservation %s is already in a final state.") % reservation.name
                )
            reservation.write({"state": "draft"})
        return {"type": "ir.actions.act_window_close"}


class ReservationReleaseWizardLine(models.TransientModel):
    """Individual line in release wizard."""

    _name = "reservation.release.wizard.line"
    _description = "Reservation Release Wizard Line"

    wizard_id = fields.Many2one(
        comodel_name="reservation.release.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    reservation_id = fields.Many2one(
        comodel_name="stock.reservation",
        string="Reservation",
        required=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product",
        required=True,
        readonly=True,
    )
    reserve_qty = fields.Float(string="Reserved Qty", readonly=True)
    allocated_qty = fields.Float(string="Allocated Qty", readonly=True)
    released_qty = fields.Float(string="Already Released", readonly=True)
    to_release = fields.Boolean(string="Release", default=True)
