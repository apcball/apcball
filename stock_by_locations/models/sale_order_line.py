# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from collections import defaultdict

from odoo import fields, models, api


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    picking_type_id = fields.Many2one(
        related='order_id.picking_type_id',
    )
    src_location_id = fields.Many2one(
        comodel_name='stock.location',
        related='order_id.picking_type_id.default_location_src_id'
    )
    purchase_price = fields.Float(
        string="Cost", compute="_compute_purchase_price",
        digits='Product Price', store=True, readonly=False, copy=False, precompute=True,
        groups="base.group_user")

    @api.depends('product_id', 'company_id', 'currency_id', 'product_uom', 'src_location_id')
    def _compute_purchase_price(self):
        for line in self:
            if not line.product_id:
                line.purchase_price = 0.0
                continue
            line = line.with_company(line.company_id)

            domain = [('company_id', '=', self.env.company.id)]
            if line.src_location_id:
                domain.append(('location_id', '=',line.src_location_id.id))
            cost_histories = line.product_id.product_cost_ids.filtered_domain(
                domain)

            product_cost = cost_histories[0].standard_price if cost_histories else 0.0

            line.purchase_price = line._convert_to_sol_currency(
                product_cost,
                line.product_id.cost_currency_id)

    @api.depends(
        'product_id', 'customer_lead', 'product_uom_qty', 'product_uom',
        'order_id.commitment_date',
        'move_ids', 'move_ids.forecast_expected_date',
        'move_ids.forecast_availability')
    def _compute_qty_at_date(self):
        """
        inherit to calculate qty available based on location
        """
        super(SaleOrderLine, self)._compute_qty_at_date()
        self = self.filtered(
            lambda rec: rec.order_id.picking_type_id and rec.order_id.picking_type_id.default_location_src_id)
        treated = self.browse()
        # If the state is already in sale the picking is created and a simple forecasted quantity isn't enough
        # Then used the forecasted data of the related stock.move
        for line in self.filtered(lambda l: l.state == 'sale'):
            if not line.display_qty_widget:
                continue
            moves = line.move_ids.filtered(
                lambda m: m.product_id == line.product_id)
            line.forecast_expected_date = max(
                moves.filtered("forecast_expected_date").mapped(
                    "forecast_expected_date"), default=False)
            line.qty_available_today = 0
            line.free_qty_today = 0
            for move in moves:
                line.qty_available_today += move.product_uom._compute_quantity(
                    move.quantity, line.product_uom)
                line.free_qty_today += move.product_id.uom_id._compute_quantity(
                    move.forecast_availability, line.product_uom)
            line.scheduled_date = line.order_id.commitment_date or line._expected_date()
            line.virtual_available_at_date = False
            treated |= line

        qty_processed_per_product = defaultdict(lambda: 0)
        grouped_lines = defaultdict(lambda: self.env['sale.order.line'])
        # We first loop over the SO lines to group them by warehouse and schedule
        # date in order to batch the read of the quantities computed field.
        for line in self.filtered(lambda l: l.state in ('draft', 'sent')):
            if not (line.product_id and line.display_qty_widget):
                continue
            grouped_lines[(line.warehouse_id.id, line.picking_type_id.default_location_src_id.id,
                           line.order_id.commitment_date or line._expected_date())] |= line

        for (warehouse, src_location, scheduled_date), lines in grouped_lines.items():
            product_qties = lines.mapped('product_id').with_context(
                to_date=scheduled_date, location=src_location).read([
                'qty_available',
                'free_qty',
                'virtual_available',
            ])
            qties_per_product = {
                product['id']: (product['qty_available'], product['free_qty'],
                                product['virtual_available'])
                for product in product_qties
            }
            for line in lines:
                line.scheduled_date = scheduled_date
                qty_available_today, free_qty_today, virtual_available_at_date = \
                    qties_per_product[line.product_id.id]
                line.qty_available_today = qty_available_today - \
                                           qty_processed_per_product[
                                               line.product_id.id]
                line.free_qty_today = free_qty_today - \
                                      qty_processed_per_product[
                                          line.product_id.id]
                line.virtual_available_at_date = virtual_available_at_date - \
                                                 qty_processed_per_product[
                                                     line.product_id.id]
                line.forecast_expected_date = False
                product_qty = line.product_uom_qty
                if line.product_uom and line.product_id.uom_id and line.product_uom != line.product_id.uom_id:
                    line.qty_available_today = line.product_id.uom_id._compute_quantity(
                        line.qty_available_today, line.product_uom)
                    line.free_qty_today = line.product_id.uom_id._compute_quantity(
                        line.free_qty_today, line.product_uom)
                    line.virtual_available_at_date = line.product_id.uom_id._compute_quantity(
                        line.virtual_available_at_date, line.product_uom)
                    product_qty = line.product_uom._compute_quantity(
                        product_qty, line.product_id.uom_id)
                qty_processed_per_product[line.product_id.id] += product_qty
            treated |= lines
        remaining = (self - treated)
        remaining.virtual_available_at_date = False
        remaining.scheduled_date = False
        remaining.forecast_expected_date = False
        remaining.free_qty_today = False
        remaining.qty_available_today = False
