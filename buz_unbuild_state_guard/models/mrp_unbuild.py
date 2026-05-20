# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpUnbuild(models.Model):
    _inherit = "mrp.unbuild"

    picking_id = fields.Many2one(
        "stock.picking",
        string="Picking",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    picking_count = fields.Integer(
        string="Picking Count",
        compute="_compute_picking_count",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("picking", "Picking"),
            ("confirm", "Confirmed"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        copy=False,
    )

    @api.depends("picking_id")
    def _compute_picking_count(self):
        for record in self:
            record.picking_count = 1 if record.picking_id else 0

    def action_create_picking(self):
        """Draft → Picking: create an internal picking to move the product."""
        self.ensure_one()

        if self.state != "draft":
            raise UserError(_("You can only create a picking from a draft unbuild order."))

        if self.picking_id:
            return self.action_view_picking()

        picking_type = self.env["stock.picking.type"].search(
            [
                ("code", "=", "internal"),
                ("company_id", "in", [False, self.company_id.id]),
            ],
            limit=1,
        )
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search(
                [("code", "=", "internal")],
                limit=1,
            )
        if not picking_type:
            raise UserError(_("No internal picking type could be found."))

        source_location = False
        if "location_id" in self._fields and self.location_id:
            source_location = self.location_id
        if not source_location:
            source_location = (
                picking_type.default_location_src_id
                or self.env.ref("stock.stock_location_stock", raise_if_not_found=False)
            )

        destination_location = False
        if "location_dest_id" in self._fields and self.location_dest_id:
            destination_location = self.location_dest_id
        if not destination_location:
            destination_location = (
                picking_type.default_location_dest_id
                or self.env.ref("stock.stock_location_production", raise_if_not_found=False)
                or source_location
            )

        if not source_location or not destination_location:
            raise UserError(_("Please configure source and destination locations for the picking."))

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": source_location.id,
                "location_dest_id": destination_location.id,
                "origin": self.display_name,
                "company_id": self.company_id.id,
                "scheduled_date": fields.Datetime.now(),
                "unbuild_id": self.id,
            }
        )

        product_uom = (
            self.product_uom_id
            if "product_uom_id" in self._fields and self.product_uom_id
            else self.product_id.uom_id
        )
        self.env["stock.move"].create(
            {
                "name": self.product_id.display_name,
                "product_id": self.product_id.id,
                "product_uom_qty": self.product_qty,
                "product_uom": product_uom.id,
                "location_id": source_location.id,
                "location_dest_id": destination_location.id,
                "picking_id": picking.id,
                "company_id": self.company_id.id,
            }
        )

        self.write(
            {
                "picking_id": picking.id,
                "state": "picking",
            }
        )
        return self.action_view_picking()

    def action_cancel_picking(self):
        """Picking → Draft: cancel linked picking."""
        self.ensure_one()
        if self.state != "picking":
            raise UserError(_("You can only cancel from the Picking state."))
        if self.picking_id and self.picking_id.state != "done":
            self.picking_id.action_cancel()
        self.write({"state": "draft"})
        return True

    def action_view_picking(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("There is no linked picking yet."))

        return {
            "type": "ir.actions.act_window",
            "name": _("Picking"),
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.picking_id.id,
            "target": "current",
        }

    def _perform_done(self):
        """Run standard Odoo unbuild logic (BOM explosion + stock moves).

        Before calling super().action_unbuild(), sync location_id to where
        the product actually is after the picking was validated — otherwise
        the standard unbuild will try to consume from the original location
        which is now empty.
        """
        for record in self:
            if record.picking_id and record.picking_id.state != "done":
                raise UserError(_("Please validate the linked picking first."))
            # Product was moved by picking to destination — unbuild must consume from there
            if record.picking_id:
                record.write({"location_id": record.picking_id.location_dest_id.id})

        # Standard Odoo: BOM explosion + produce components + consume product
        res = super().action_unbuild()
        return res

    def action_confirm_done(self):
        """Confirm → Done: execute standard unbuild (BOM explosion + stock moves)."""
        for record in self:
            if record.state != "confirm":
                raise UserError(_("You can only confirm done from the Confirmed state."))
        return self._perform_done()

    def action_unbuild(self):
        """Block direct unbuild — must go through picking flow or confirm."""
        confirmed = self.filtered(lambda r: r.state == "confirm")
        if confirmed:
            return confirmed._perform_done()
        raise UserError(_("Use the linked picking to complete this unbuild order."))

    def action_done(self):
        """Block direct done — must go through picking flow or confirm."""
        confirmed = self.filtered(lambda r: r.state == "confirm")
        if confirmed:
            return confirmed._perform_done()
        raise UserError(_("Use the linked picking to complete this unbuild order."))
