import logging

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_round

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _cal_price(self, consumed_moves):
        """Recompute finished/by-product price using the FULL raw cost.

        Core (``mrp_account``) bases ``total_cost`` on ``consumed_moves``,
        which is only the raw moves that turned 'done' in *this*
        ``_post_inventory`` call. When raw materials are consumed in
        separate steps (e.g. validated one component at a time before the
        final "Mark as Done"), moves already done from an earlier step are
        silently excluded from ``consumed_moves`` - their cost disappears
        from the split entirely, so by-products end up valued against a
        partial total instead of the true total production cost.
        """
        res = super()._cal_price(consumed_moves)
        finished_move = self.move_finished_ids.filtered(
            lambda x: x.product_id == self.product_id
            and x.state not in ("done", "cancel")
            and x.quantity > 0
        )
        if not finished_move:
            return res
        finished_move.ensure_one()

        work_center_cost = sum(
            work_order._cal_cost() for work_order in self.workorder_ids
        )
        quantity = finished_move.product_uom._compute_quantity(
            finished_move.quantity, finished_move.product_id.uom_id
        )
        extra_cost = self.extra_cost * quantity
        raw_moves = self.move_raw_ids.filtered(lambda m: m.state != "cancel")
        total_cost = (
            -sum(raw_moves.sudo().stock_valuation_layer_ids.mapped("value"))
            + work_center_cost
            + extra_cost
        )

        byproduct_moves = self.move_byproduct_ids.filtered(
            lambda m: m.state not in ("done", "cancel") and m.quantity > 0
        )
        byproduct_cost_share = 0
        for byproduct in byproduct_moves:
            if byproduct.cost_share == 0:
                continue
            byproduct_cost_share += byproduct.cost_share
            if byproduct.product_id.cost_method in ("fifo", "average"):
                byproduct.price_unit = (
                    total_cost
                    * byproduct.cost_share
                    / 100
                    / byproduct.product_uom._compute_quantity(
                        byproduct.quantity, byproduct.product_id.uom_id
                    )
                )
        if finished_move.product_id.cost_method in ("fifo", "average"):
            finished_move.price_unit = (
                total_cost
                * float_round(1 - byproduct_cost_share / 100, precision_rounding=0.0001)
                / quantity
            )
        return res

    def button_mark_done(self):
        for production in self:
            zero_cost_moves = production.move_byproduct_ids.filtered(
                lambda m: m.state != "cancel"
                and float_is_zero(m.cost_share, precision_digits=2)
            )
            if zero_cost_moves:
                product_names = ", ".join(zero_cost_moves.mapped("product_id.name"))
                raise UserError(
                    _(
                        "ไม่สามารถผลิตได้ เนื่องจากผลิตภัณฑ์พลอยได้ (By-product) ยังไม่ได้กำหนดสัดส่วนต้นทุน (Cost Share)\n"
                        "กรุณากำหนด Cost Share ให้กับสินค้า: %s"
                    )
                    % product_names
                )
        res = super().button_mark_done()
        for production in self:
            if production.state == "done":
                production._check_byproduct_cost_balance()
        return res

    def _check_byproduct_cost_balance(self):
        """Safety net: flag any MO whose finished + by-product valuation
        doesn't add up to raw cost + operation cost, in case a future
        change (core patch, other override, rounding edge case) reopens
        the cost-split bug that ``_cal_price`` above fixes."""
        self.ensure_one()
        byproduct_moves = self.move_byproduct_ids.filtered(lambda m: m.state == "done")
        if not byproduct_moves:
            return
        finished_move = self.move_finished_ids.filtered(
            lambda m: m.product_id == self.product_id and m.state == "done"
        )
        output_value = sum(
            (finished_move | byproduct_moves).sudo().stock_valuation_layer_ids.mapped("value")
        )
        raw_moves = self.move_raw_ids.filtered(lambda m: m.state == "done")
        raw_cost = -sum(raw_moves.sudo().stock_valuation_layer_ids.mapped("value"))
        work_center_cost = sum(work_order._cal_cost() for work_order in self.workorder_ids)
        quantity = (
            finished_move.product_uom._compute_quantity(
                finished_move.quantity, finished_move.product_id.uom_id
            )
            if finished_move
            else 0.0
        )
        extra_cost = self.extra_cost * quantity
        expected_total = raw_cost + work_center_cost + extra_cost
        diff = output_value - expected_total
        if float_is_zero(diff, precision_digits=2):
            return
        message = _(
            "คำเตือน: ต้นทุนของ By-product ใน MO นี้อาจไม่ถูกต้อง\n"
            "มูลค่ารวม Finished + By-product = %(output).2f\n"
            "ต้นทุนที่ควรจะเป็น (raw + operation) = %(expected).2f\n"
            "ผลต่าง = %(diff).2f\n"
            "กรุณาตรวจสอบ stock.valuation.layer ของ MO นี้",
            output=output_value,
            expected=expected_total,
            diff=diff,
        )
        _logger.warning(
            "MO %s: by-product cost mismatch, output=%.2f expected=%.2f diff=%.2f",
            self.name, output_value, expected_total, diff,
        )
        self.message_post(body=message)
