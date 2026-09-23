from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Override Odoo's margin field to use standard cost calculation
    margin = fields.Monetary(
        string="Margin",
        compute='_compute_margin',
        store=True,
        currency_field='currency_id'
    )
    
    @api.depends('order_line.margin', 'amount_untaxed')
    def _compute_margin(self):
        for order in self:
            order.margin = sum(order.order_line.mapped('margin'))
            order.margin_percent = order.amount_untaxed and order.margin / order.amount_untaxed

    missing_cost_warning = fields.Text(compute='_compute_missing_cost_warning')

    @api.depends('order_line.purchase_price', 'order_line.product_id', 'order_line.display_type', 'order_line.is_downpayment')
    def _compute_missing_cost_warning(self):
        for order in self:
            missing = order._get_missing_cost_products()
            order.missing_cost_warning = _(
                "สินค้าต่อไปนี้ยังไม่มี Cost กรุณาแจ้งบัญชีต้นทุนให้ตั้งราคาต้นทุนใน Standard Cost Pricelist ก่อน Confirm:\n%s"
            ) % "\n".join("- %s" % name for name in missing) if missing else False

    def _get_missing_cost_products(self):
        self.ensure_one()
        return [
            line.product_id.display_name
            for line in self.order_line
            if not line.display_type and not line.is_downpayment and line.product_id and line.purchase_price <= 0
        ]

    def action_confirm(self):
        # Validation checks
        get_param = self.env['ir.config_parameter'].sudo().get_param
        min_margin = float(get_param('sale_pricelist_standard_cost.minimum_margin_percent', default=0.0))
        block_negative = get_param('sale_pricelist_standard_cost.block_negative_margin') == 'True'

        for order in self:
            # Check Missing Standard Cost (block confirm, product must have cost set first)
            missing_cost_products = order._get_missing_cost_products()

            if missing_cost_products:
                raise ValidationError(_(
                    "ไม่สามารถ Confirm ได้: สินค้าต่อไปนี้ยังไม่มี Standard Cost กรุณาแจ้งบัญชีต้นทุนให้ตั้งราคาต้นทุนใน Standard Cost Pricelist ก่อน:\n%s"
                ) % "\n".join("- %s" % name for name in missing_cost_products))

            # Check Global Margin
            if min_margin > 0:
                # Compare as percent (e.g. 10.0 for 10%)
                if order.amount_untaxed:
                    current_margin_pct = (order.margin / order.amount_untaxed) * 100
                else:
                    current_margin_pct = 0.0
                if current_margin_pct < min_margin:
                     raise ValidationError(_("Order margin (%.2f%%) is below the minimum required (%.2f%%).") % (current_margin_pct, min_margin))

            # Check Negative Margin (Line by line)
            if block_negative:
                for line in order.order_line:
                    if not line.is_downpayment and line.display_type == False and line.margin < 0:
                         raise ValidationError(_("Line for %s has negative margin, which is blocked.") % line.product_id.name)
                         
        return super(SaleOrder, self).action_confirm()
