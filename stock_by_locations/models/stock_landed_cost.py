# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from collections import defaultdict
from odoo.exceptions import UserError
from odoo.tools import float_is_zero
from odoo import models, fields, api, _


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    origin = fields.Char(string='Source Document', compute="_compute_source_document")
    smart_button_visible_so = fields.Boolean(compute="_compute_source_document")
    source_doc_count_so = fields.Integer(
        string='Source Doc Count',
        compute='_compute_source_document',
    )
    smart_button_visible_po = fields.Boolean(compute="_compute_source_document")
    source_doc_count_po = fields.Integer(
        string='Source Doc Count',
        compute='_compute_source_document',
    )
    vendor_bill_ids = fields.Many2many(
        'account.move', copy=False, domain=[('move_type', '=', 'in_invoice')], compute="_compute_landed_cost_bill")

    def _compute_landed_cost_bill(self):
        for rec in self:
            bills = rec.mapped('picking_ids.landed_cost_line_ids.account_move_line_ids.move_id')
            if bills:
                rec.vendor_bill_ids = bills.ids
            else:
                rec.vendor_bill_ids = False

    def _compute_source_document(self):
        for rec in self:
            if rec.picking_ids:
                source_po = rec.picking_ids.filtered(lambda o: o.origin and o.purchase_id).mapped('origin')
                source_so = rec.picking_ids.filtered(lambda o: o.origin and o.sale_id).mapped('origin')
                source = rec.picking_ids.filtered(lambda o: o.origin).mapped('origin')
                if source:
                    rec.origin = ', '.join(source)
                    if source_po:
                        rec.smart_button_visible_po = True
                        rec.source_doc_count_po = len(source_po)
                    else:
                        rec.smart_button_visible_po = False
                        rec.source_doc_count_po = 0
                    if source_so:
                        rec.smart_button_visible_so = True
                        rec.source_doc_count_so = len(source_so)
                    else:
                        rec.smart_button_visible_so = False
                        rec.source_doc_count_so = 0
                else:
                    rec.origin = ''
                    rec.smart_button_visible_so = False
                    rec.source_doc_count_so = 0
                    rec.smart_button_visible_po = False
                    rec.source_doc_count_po = 0
            else:
                rec.origin = ''
                rec.smart_button_visible_so = False
                rec.source_doc_count_so = 0
                rec.smart_button_visible_po = False
                rec.source_doc_count_po = 0

    def action_view_source_document_po(self):
        """ Return the action for the views of the Purchase Order linked to the transaction.

        Note: self.ensure_one()

        :return: The action
        :rtype: dict
        """
        self.ensure_one()
        action = {}
        source_ids = False
        if self.picking_ids:
            source_po = self.picking_ids.filtered(lambda o: o.origin and o.purchase_id)
            if source_po:
                if source_po:
                    action = {
                        'name': _("Purchase Order"),
                        'type': 'ir.actions.act_window',
                        'res_model': 'purchase.order',
                        'target': 'current',
                    }
                    source_ids = source_po.purchase_id.mapped('id')
            if source_ids and len(source_ids) == 1:
                action['res_id'] = source_ids[0]
                action['view_mode'] = 'form'
                action['views'] = [(self.env.ref('purchase.purchase_order_form').id, 'form')]
            else:
                action['view_mode'] = 'tree,form'
                action['domain'] = [('id', 'in', source_ids)]
        return action

    def action_view_source_document_so(self):
        """ Return the action for the views of the Sale Order linked to the transaction.

        Note: self.ensure_one()

        :return: The action
        :rtype: dict
        """
        self.ensure_one()
        action = {}
        source_ids = False
        if self.picking_ids:
            source_so = self.picking_ids.filtered(lambda o: o.origin and o.sale_id)
            if source_so:
                if source_so:
                    action = {
                        'name': _("Sale Order"),
                        'type': 'ir.actions.act_window',
                        'res_model': 'sale.order',
                        'target': 'current',
                    }
                    source_ids = source_so.sale_id.mapped('id')
            if source_ids and len(source_ids) == 1:
                action['res_id'] = source_ids[0]
                action['view_mode'] = 'form'
                action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
            else:
                action['view_mode'] = 'tree,form'
                action['domain'] = [('id', 'in', source_ids)]
        return action

    def get_valuation_lines(self):
        self.ensure_one()
        lines = []

        for move in self._get_targeted_move_ids():
            # it doesn't make sense to make a landed cost for a product that isn't set as being valuated in real time at real cost
            if move.product_id.valuation != 'real_time' or move.product_id.cost_method not in ('fifo', 'average', 'avco_by_location') or move.state == 'cancel' or not move.quantity:
                continue

            former_cost = sum(move._get_stock_valuation_layer_ids().mapped('value'))
            if move.picking_id.picking_type_id.code in ['incoming', 'outgoing']:
                former_cost = sum(move.stock_valuation_layer_ids.mapped('value'))
            elif move.picking_id.picking_type_id.code == 'internal':
                former_cost = sum(move.stock_valuation_layer_ids.filtered(
                    lambda svl: svl.location_id == move.location_dest_id).mapped('value'))
            qty = move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id)
            vals = {
                'product_id': move.product_id.id,
                'move_id': move.id,
                'quantity': qty,
                'former_cost':former_cost,
                'weight': move.product_id.weight * qty,
                'volume': move.product_id.volume * qty
            }
            lines.append(vals)

        if not lines:
            target_model_descriptions = dict(self._fields['target_model']._description_selection(self.env))
            raise UserError(
                _("You cannot apply landed costs on the chosen %s(s). Landed costs can only be applied for products with FIFO or average costing method.",
                  target_model_descriptions[self.target_model]))
        return lines

    def button_validate(self):
        self._check_can_validate()
        cost_without_adjusment_lines = self.filtered(lambda c: not c.valuation_adjustment_lines)
        if cost_without_adjusment_lines:
            cost_without_adjusment_lines.compute_landed_cost()
        if not self._check_sum():
            raise UserError(_('Cost and adjustments lines do not match. You should maybe recompute the landed costs.'))

        for cost in self:
            cost = cost.with_company(cost.company_id)
            warehouse_id = self.env['stock.warehouse'].search(
                [('is_main_warehouse', '=', True), '|', ('company_id', '=', cost.company_id.id),
                 ('company_id', '=', False)], limit=1)
            main_location_id = False
            if warehouse_id:
                main_location_id = warehouse_id.lot_stock_id
            move = self.env['account.move']
            move_vals = {
                'journal_id': cost.account_journal_id.id,
                'date': cost.date,
                'ref': cost.name,
                'line_ids': [],
                'move_type': 'entry',
            }
            valuation_layer_ids = []
            cost_to_add_byproduct = defaultdict(lambda: 0.0)
            cost_to_add_bylot = defaultdict(lambda: defaultdict(float))
            for line in cost.valuation_adjustment_lines.filtered(lambda line: line.move_id):
                remaining_qty = sum(line.move_id._get_stock_valuation_layer_ids().mapped('remaining_qty'))
                if line.move_id.picking_id.picking_type_id.code in ['incoming', 'outgoing']:
                    remaining_qty = sum(line.move_id.stock_valuation_layer_ids.mapped('remaining_qty'))
                elif line.move_id.picking_id.picking_type_id.code == 'internal':
                    remaining_qty = sum(line.move_id.stock_valuation_layer_ids.filtered(
                        lambda svl: svl.location_id == line.move_id.location_dest_id).mapped('remaining_qty'))
                linked_layer = line.move_id._get_stock_valuation_layer_ids()

                # Prorate the value at what's still in stock
                move_qty = line.move_id.product_uom._compute_quantity(line.move_id.quantity,
                                                                      line.move_id.product_id.uom_id)
                cost_to_add = (remaining_qty / move_qty) * line.additional_landed_cost
                product = line.move_id.product_id
                if not cost.company_id.currency_id.is_zero(cost_to_add):
                    vals_list = []
                    if line.move_id.product_id.lot_valuated:
                        for lot_id, sml in line.move_id.move_line_ids.grouped('lot_id').items():
                            lot_layer = linked_layer.filtered(lambda l: l.lot_id == lot_id)[:1]
                            value = cost_to_add * sum(sml.mapped('quantity')) / line.move_id.quantity
                            if product.cost_method in ['average', 'fifo']:
                                cost_to_add_bylot[product][lot_id] += value

                            vals_list.append({
                                'value': value,
                                'unit_cost': 0,
                                'quantity': 0,
                                'remaining_qty': 0,
                                'stock_valuation_layer_id': lot_layer.id,
                                'description': cost.name,
                                'stock_move_id': line.move_id.id,
                                'product_id': line.move_id.product_id.id,
                                'stock_landed_cost_id': cost.id,
                                'company_id': cost.company_id.id,
                                'lot_id': lot_id.id,
                            })
                            lot_layer.remaining_value += value
                    else:
                        vals_list.append({
                            'value': cost_to_add,
                            'unit_cost': 0,
                            'quantity': 0,
                            'remaining_qty': 0,
                            'stock_valuation_layer_id': linked_layer[:1].id,
                            'description': cost.name,
                            'stock_move_id': line.move_id.id,
                            'product_id': line.move_id.product_id.id,
                            'stock_landed_cost_id': cost.id,
                            'company_id': cost.company_id.id,
                        })
                        linked_layer[:1].remaining_value += cost_to_add
                    valuation_layer = self.env['stock.valuation.layer'].create(vals_list)
                    valuation_layer_ids += valuation_layer.ids
                # Update the AVCO/FIFO
                if product.cost_method in ['average', 'fifo']:
                    cost_to_add_byproduct[product] += cost_to_add
                if product.cost_method == 'avco_by_location':
                    if main_location_id and linked_layer and linked_layer[:1].location_id:
                        if linked_layer[:1].location_id.id in main_location_id.child_ids.ids or linked_layer[:1].location_id == main_location_id:
                            cost_to_add_byproduct[product] += cost_to_add
                # Products with manual inventory valuation are ignored because they do not need to create journal entries.
                if product.valuation != "real_time":
                    continue
                # `remaining_qty` is negative if the move is out and delivered proudcts that were not
                # in stock.
                qty_out = 0
                if line.move_id._is_in():
                    qty_out = line.move_id.quantity - remaining_qty
                elif line.move_id._is_out():
                    qty_out = line.move_id.quantity
                move_vals['line_ids'] += line._create_accounting_entries(move, qty_out)

            # batch standard price computation avoid recompute quantity_svl at each iteration
            products = self.env['product.product'].browse(p.id for p in cost_to_add_byproduct.keys()).with_company(
                cost.company_id)
            for product in products:  # iterate on recordset to prefetch efficiently quantity_svl

                if product.cost_method == 'avco_by_location' and main_location_id:
                    if not float_is_zero(product.with_context(force_location_id=main_location_id.id).quantity_svl,
                                         precision_rounding=product.uom_id.rounding):
                        product.with_company(cost.company_id).sudo().with_context(
                            disable_auto_svl=True).standard_price += \
                            cost_to_add_byproduct[product] / product.with_context(
                                force_location_id=main_location_id.id).quantity_svl

                else:

                    if not float_is_zero(product.quantity_svl, precision_rounding=product.uom_id.rounding):
                        product.sudo().with_context(disable_auto_svl=True).standard_price += cost_to_add_byproduct[
                                                                                                 product] / product.quantity_svl
                    if product.lot_valuated:
                        for lot, value in cost_to_add_bylot[product].items():
                            if float_is_zero(lot.quantity_svl, precision_rounding=product.uom_id.rounding):
                                continue
                            lot.sudo().with_context(disable_auto_svl=True).standard_price += value / lot.quantity_svl

            move_vals['stock_valuation_layer_ids'] = [(6, None, valuation_layer_ids)]
            # We will only create the accounting entry when there are defined lines (the lines will be those linked to products of real_time valuation category).
            cost_vals = {'state': 'done'}
            if move_vals.get("line_ids"):
                move = move.create(move_vals)
                cost_vals.update({'account_move_id': move.id})
            cost.write(cost_vals)
            if cost.account_move_id:
                move._post()
            cost.reconcile_landed_cost()
        return True
