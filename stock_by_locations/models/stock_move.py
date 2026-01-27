# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from collections import defaultdict

from odoo import api, fields, models
from odoo.tools import float_is_zero, OrderedSet


class StockMove(models.Model):
    _inherit = "stock.move"

    def _create_internal_svl(self, forced_quantity=None):
        """Create a `stock.valuation.layer` from `self`.

        :param forced_quantity: under some circunstances, the quantity to value is different than
            the initial demand of the move (Default value = None)
        """
        svl_vals_list = []
        stock_valuation_layers = self.env["stock.valuation.layer"]
        for move in self:
            move = move.with_company(move.company_id)
            valued_move_lines = move._get_internal_move_lines()
            valued_quantity = 0
            for valued_move_line in valued_move_lines:
                valued_quantity += valued_move_line.product_uom_id._compute_quantity(valued_move_line.qty_done,
                                                                                     move.product_id.uom_id)

            new_std_price = move._get_price_unit()  # May be negative (i.e. decrease an out move).
            unit_cost = abs(next(iter(new_std_price.values())))

            in_svl_vals = move.product_id._prepare_internal_in_svl_vals(forced_quantity or valued_quantity, unit_cost,
                                                                        move)
            if forced_quantity:
                in_svl_vals[
                    'description'] = 'Correction of %s (modification of past move)' % move.picking_id.name or move.name
            if 'rounding_adjustment' in in_svl_vals:
                in_svl_vals.pop('rounding_adjustment')
            svl_vals_list.append(in_svl_vals)

            out_svl_vals = move.product_id._prepare_internal_out_svl_vals(forced_quantity or valued_quantity,
                                                                          move.company_id, move)
            if 'rounding_adjustment' in out_svl_vals:
                out_svl_vals.pop('rounding_adjustment')
            if forced_quantity:
                out_svl_vals[
                    'description'] = 'Correction of %s (modification of past move)' % move.picking_id.name or move.name
            svl_vals_list.append(out_svl_vals)
        if svl_vals_list:
            stock_valuation_layers = self.env["stock.valuation.layer"].sudo().create(svl_vals_list)
        return stock_valuation_layers

    def _get_internal_move_lines(self):
        """ Returns the `stock.move.line` records of `self` considered as incoming. It is done thanks
        to the `_should_be_valued` method of their source and destionation location as well as their
        owner.

        :returns: a subset of `self` containing the incoming records
        :rtype: recordset
        """
        self.ensure_one()
        res = OrderedSet()
        for move_line in self.move_line_ids:
            if move_line.owner_id and move_line.owner_id != move_line.company_id.partner_id:
                continue
            if move_line.location_id._should_be_valued() and move_line.location_dest_id._should_be_valued():
                res.add(move_line.id)
        return self.env['stock.move.line'].browse(res)

    def _is_internal(self):
        """Check if the move should be considered as entering the company so that the cost method
        will be able to apply the correct logic.

        :returns: True if the move is entering the company else False
        :rtype: bool
        """
        self.ensure_one()
        if self._get_internal_move_lines():
            return True
        return False

    @api.model
    def _get_valued_types(self):
        res = super(StockMove, self)._get_valued_types()
        res.append('internal')
        return res

    def _prepare_common_svl_vals(self):
        vals = super(StockMove, self)._prepare_common_svl_vals()
        if self._is_in():
            vals.update({
                'location_id': self.location_dest_id.id,
            })
        else:
            vals.update({
                'location_id': self.location_id.id,
            })
        vals.update({
            'description': self.reference and '%s - %s' % (
                self.reference, self.product_id.display_name) or self.product_id.display_name,
        })
        return vals

    def _get_out_svl_vals(self, forced_quantity):
        svl_vals_list = []
        for move in self:
            move = move.with_company(move.company_id)
            lines = move._get_out_move_lines()
            quantities = defaultdict(float)
            if forced_quantity:
                quantities[forced_quantity[0]] += forced_quantity[1]
            else:
                for line in lines:
                    quantities[line.lot_id] += line.quantity_product_uom
            if float_is_zero(sum(quantities.values()), precision_rounding=move.product_id.uom_id.rounding):
                continue

            if move.product_id.lot_valuated:
                vals = []
                for lot_id, qty in quantities.items():
                    out_vals = move.product_id._prepare_out_svl_vals(
                        qty,
                        move.company_id,
                        lot=lot_id,
                        location=move.location_id
                    )
                    vals.append(out_vals)
            else:
                vals = [move.product_id._prepare_out_svl_vals(sum(quantities.values()), move.company_id, location=move.location_id)]
            for val in vals:
                val.update(move._prepare_common_svl_vals())
                if forced_quantity:
                    val['description'] = _('Correction of %s (modification of past move)', move.picking_id.name or move.name)
                val['description'] += val.pop('rounding_adjustment', '')
            svl_vals_list += vals
        return svl_vals_list

    # def _create_out_svl(self, forced_quantity=None):
    #     """Create a `stock.valuation.layer` from `self`.
    #
    #     :param forced_quantity: under some circunstances, the quantity to value is different than
    #         the initial demand of the move (Default value = None)
    #     """
    #     svl_vals_list = []
    #     for move in self:
    #         move = move.with_company(move.company_id)
    #         valued_move_lines = move._get_out_move_lines()
    #         valued_quantity = 0
    #         for valued_move_line in valued_move_lines:
    #             valued_quantity += valued_move_line.product_uom_id._compute_quantity(valued_move_line.qty_done,
    #                                                                                  move.product_id.uom_id)
    #         if float_is_zero(forced_quantity or valued_quantity, precision_rounding=move.product_id.uom_id.rounding):
    #             continue
    #
    #         svl_vals = move.product_id._prepare_out_svl_vals(forced_quantity or valued_quantity, move.company_id,
    #                                                          move.location_id)
    #         svl_vals.update(move._prepare_common_svl_vals())
    #         if forced_quantity:
    #             svl_vals[
    #                 'description'] = 'Correction of %s (modification of past move)' % move.picking_id.name or move.name
    #         svl_vals['description'] += svl_vals.pop('rounding_adjustment', '')
    #         svl_vals_list.append(svl_vals)
    #     return self.env['stock.valuation.layer'].sudo().create(svl_vals_list)

    def _is_main_location_internal(self):
        """
        return true if move is related to main warehouse location and source
        location is internal
        :return: Boolean
        """
        self.ensure_one()
        warehouse_id = self.env['stock.warehouse'].search(
            [('is_main_warehouse', '=', True), '|',
             ('company_id', '=', self.company_id.id),
             ('company_id', '=', False)], limit=1)
        main_location_id = False
        if warehouse_id:
            main_location_id = warehouse_id.lot_stock_id

        if main_location_id:
            if self.location_dest_id.id in main_location_id.child_ids.ids \
                    or self.location_dest_id == main_location_id and self.location_id.usage == 'internal':
                return True
        return False

    def product_price_update_before_done(self, forced_qty=None):
        """ inherit to update standard price based on main warehouse flag and cost method is avco_by_location"""
        super(StockMove, self).product_price_update_before_done(forced_qty)
        tmpl_dict = defaultdict(lambda: 0.0)
        std_price_update = {}
        for move in self.filtered(lambda move: move._is_in() or move._is_internal()
                                               and move.with_company(
            move.company_id).product_id.cost_method == 'avco_by_location'):

            # Get the standard price
            standard_price = move.product_id.with_company(move.company_id).get_last_cost_history(
                location=move.location_dest_id)
            amount_unit = std_price_update.get((move.company_id.id, move.product_id.id)) or standard_price

            product_tot_qty_available = move.product_id.sudo().with_company(
                move.company_id).with_context(force_location_id=move.location_dest_id.id).quantity_svl \
                                        + tmpl_dict[move.product_id.id]
            rounding = move.product_id.uom_id.rounding
            valued_move_lines = self.env['stock.move.line']
            if move._is_in():
                valued_move_lines = move._get_in_move_lines()
            elif move._is_internal():
                valued_move_lines = move._get_internal_move_lines()
            qty_done = 0
            for valued_move_line in valued_move_lines:
                qty_done += valued_move_line.product_uom_id._compute_quantity(
                    valued_move_line.qty_done, move.product_id.uom_id)

            qty = forced_qty or qty_done
            new_unit_price = move._get_price_unit()  # return cost for product include landed cost for move is in only
            if float_is_zero(product_tot_qty_available, precision_rounding=rounding):
                new_std_price = next(iter(new_unit_price.values()))
            elif float_is_zero(product_tot_qty_available + move.product_qty, precision_rounding=rounding) \
                    or float_is_zero(product_tot_qty_available + qty, precision_rounding=rounding):
                new_std_price = next(iter(new_unit_price.values()))
            else:
                new_std_price = ((amount_unit * product_tot_qty_available) + (next(iter(new_unit_price.values())) * qty)) / (
                            product_tot_qty_available + qty)
            tmpl_dict[move.product_id.id] += qty_done

            # update product cost if location dest is main
            warehouse_id = self.env['stock.warehouse'].search(
                [('is_main_warehouse', '=', True), '|',
                 ('company_id', '=', move.company_id.id),
                 ('company_id', '=', False)], limit=1)
            main_location_id = False
            if warehouse_id:
                main_location_id = warehouse_id.lot_stock_id
            # affect only if qty is positive
            if qty >= 0.0:
                if main_location_id and move.location_dest_id.id in main_location_id.child_ids.ids or move.location_dest_id == main_location_id:
                    # Write the standard price, as SUPERUSER_ID because a warehouse manager may not have the right to write on products
                    move.product_id.with_company(move.company_id.id).with_context(
                        disable_auto_svl=True).sudo().write({'standard_price': new_std_price})
                std_price_update[move.company_id.id, move.product_id.id] = new_std_price

                incoming_cost = move._get_price_unit()

                self.env['product.cost.location.history'].create({
                    'company_id': move.company_id.id,
                    'currency_id': move.company_id.currency_id.id,
                    'location_id': move.location_dest_id.id,
                    'standard_price': new_std_price,
                    'qty': product_tot_qty_available + qty,
                    'date': fields.Datetime.now(),
                    'product_id': move.product_id.id,
                    'former_qty': product_tot_qty_available,
                    'former_avg': amount_unit,
                    'incoming_qty': qty,
                    'incoming_cost': next(iter(incoming_cost.values())),
                    'move_id': move.id,
                    'name': 'Stock move: ' + move.display_name + ' - '
                            + move.product_id.display_name
                })

    def _get_price_unit(self):
        """
        inherit to adjust price to read from location not from standard price
        """
        price_unit = super(StockMove, self)._get_price_unit()
        # check if move is not in / out
        if self.location_id.usage in ['internal', 'inventory', 'production'] and \
                self.location_dest_id.usage in ['internal', 'inventory', 'production']:
            cost_history = self.product_id.get_last_cost_history(location=self.location_id)
            if cost_history and price_unit != cost_history:
                price_unit = {self.env['stock.lot']: cost_history}
        return price_unit

    def _action_done(self, cancel_backorder=False):
        """
        inherit to trigger product_price_update_before_done
        """
        valued_moves = {valued_type: self.env['stock.move'] for valued_type in
                        self._get_valued_types()}
        for move in self:
            if float_is_zero(move.quantity,
                             precision_rounding=move.product_uom.rounding):
                continue
            for valued_type in self._get_valued_types():
                if getattr(move, '_is_%s' % valued_type)() \
                        and valued_type == 'internal':
                    valued_moves[valued_type] |= move
        # AVCO by location application
        valued_moves['internal'].product_price_update_before_done()
        return super(StockMove, self)._action_done(
            cancel_backorder=cancel_backorder)
