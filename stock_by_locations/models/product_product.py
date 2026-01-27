# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, OrderedSet, float_repr



class ProductProduct(models.Model):
    _inherit = 'product.product'

    product_cost_history_ids = fields.One2many(
        comodel_name='product.cost.location.history',
        inverse_name='product_id',
    )
    product_cost_history_summary_ids = fields.Many2many(
        comodel_name='product.cost.location',
        compute='_compute_product_cost',
    )
    product_cost_exclude_history_summary_ids = fields.Many2many(
        comodel_name='product.cost.location',
        compute='_compute_product_cost',
        domain="[('exclude_from_product_cost', '=', False)]"
    )
    product_cost_ids = fields.Many2many('product.cost.location', compute='_compute_product_cost')
    product_cost_exclude_location_ids = fields.Many2many('product.cost.location', compute='_compute_product_cost',
                                                         domain="[('exclude_from_product_cost', '=', False)]")
    main_wh_cost = fields.Float(string='Main WH Cost',
                                compute='_compute_main_wh_cost')

    @api.depends_context('company')
    @api.depends('product_cost_ids', 'product_cost_history_ids', 'company_id')
    def _compute_main_wh_cost(self):
        warehouse_id = self.env['stock.warehouse'].search(
            [('is_main_warehouse', '=', True), '|',
             ('company_id', '=', self.env.company.id),
             ('company_id', '=', False)], limit=1)
        for record in self:
            if warehouse_id:
                record.main_wh_cost = record.get_last_cost_history(location=warehouse_id.lot_stock_id)
            else:
                record.main_wh_cost = 0

    @api.depends('stock_valuation_layer_ids')
    @api.depends_context('to_date', 'force_company', 'quant_location')
    def _compute_product_cost(self):
        company_id = self.env.context.get('force_company', False) or self.env.company.id
        to_date = self.env.context.get('to_date', False)
        for product in self:
            data = []
            data_exlude_location = []
            history_data = []
            history_data_exlude_location = []
            if product.cost_method in ('avco_by_location'):
                # for location_id in self.env['stock.quant'].sudo().search([('product_id', '=', product.id), ('location_id.usage', '=', 'internal')]).mapped('location_id'):
                # appear all internal location not has transaction only
                if 'quant_location' in self._context and self._context.get('quant_location'):
                    locations = self._context.get('quant_location')
                else:
                    locations = self.env['stock.location'].search([('usage', '=', 'internal')])
                for location_id in locations:
                    domain = [
                        ('product_id', '=', product.id),
                        ('company_id', '=', company_id),
                        ('location_id', 'in', location_id.ids)
                    ]
                    if to_date:
                        to_date = fields.Datetime.to_datetime(to_date)
                        domain.append(('create_date', '<=', to_date))

                    groups_qty = self.env['stock.valuation.layer'].read_group(domain, ['quantity:sum'], ['product_id'])
                    # in avg do not calculate cost of out from location
                    domain.append(('quantity', '>=', 0))
                    groups_value = self.env['stock.valuation.layer'].read_group(domain, ['value:sum', 'quantity:sum'],
                                                                                ['product_id'])
                    # appear all internal location
                    qty = 0
                    cost = 0
                    if groups_qty and groups_value:
                        qty = groups_qty[0].get('quantity')
                        if groups_value[0].get('quantity'):
                            cost = (groups_value[0].get('value') / groups_value[0].get('quantity'))
                    data.append((0, 0, {
                        'product_id': product.id,
                        'qty': qty,
                        'standard_price': cost,
                        'location_id': location_id.id,
                        'company_id': company_id,
                        'exclude_from_product_cost': location_id.exclude_from_product_cost,
                    }))
                    if self._context.get('quant_location'):
                        location = self._context.get('quant_location')
                        history_cost = product.get_last_cost_history(location=location, to_date=to_date)
                    else:
                        history_cost = product.get_last_cost_history(location=location_id, to_date=to_date)
                    history_data.append((0, 0, {
                        'product_id': product.id,
                        'qty': qty,
                        'standard_price': history_cost,
                        'location_id': location_id.id,
                        'company_id': company_id,
                        'exclude_from_product_cost': location_id.exclude_from_product_cost,
                    }))
                    if not location_id.exclude_from_product_cost:
                        data_exlude_location.append((0, 0, {
                            'product_id': product.id,
                            'qty': qty,
                            'standard_price': cost,
                            'location_id': location_id.id,
                            'company_id': company_id,
                            'exclude_from_product_cost': location_id.exclude_from_product_cost,
                        }))
                        history_data_exlude_location.append((0, 0, {
                            'product_id': product.id,
                            'qty': qty,
                            'standard_price': cost,
                            'location_id': location_id.id,
                            'company_id': company_id,
                            'exclude_from_product_cost': location_id.exclude_from_product_cost,
                        }))
            product.product_cost_ids = data
            product.product_cost_exclude_location_ids = data_exlude_location
            product.product_cost_history_summary_ids = history_data
            product.product_cost_exclude_history_summary_ids = history_data_exlude_location

    def _prepare_internal_in_svl_vals(self, quantity, unit_cost, move=False):
        self.ensure_one()
        vals = {
            'product_id': self.id,
            'quantity': quantity,
            'stock_move_id': move.id,
            'company_id': move.company_id.id,
            'description': move.reference and '%s - %s' % (move.reference, self.name) or self.name,
            'location_id': move.location_dest_id.id,
        }
        if self.cost_method in ('avco_by_location'):
            cost_id = [t for t in self.product_cost_history_summary_ids if t.location_id == move.location_dest_id]
            if cost_id:
                cost_id = cost_id[0]
                vals['remaining_qty'] = cost_id.qty + quantity
                vals['value'] = cost_id[0].standard_price * quantity
                vals['unit_cost'] = cost_id[0].standard_price
        if self.cost_method in ('average', 'fifo'):
            vals['value'] = unit_cost * quantity
            vals['remaining_qty'] = quantity
            vals['remaining_value'] = vals['value']
        return vals

    def _prepare_internal_out_svl_vals(self, quantity, company, move=False):
        self.ensure_one()
        quantity = -1 * quantity
        vals = {
            'product_id': self.id,
            'quantity': quantity,
            'value': quantity * self.standard_price,
            'unit_cost': self.standard_price,
            'stock_move_id': move.id,
            'company_id': move.company_id.id,
            'description': move.reference and '%s - %s' % (move.reference, self.name) or self.name,
            'location_id': move.location_id.id
        }
        if self.cost_method in ('avco_by_location'):
            cost_id = [t for t in self.product_cost_history_summary_ids if t.location_id == move.location_id]
            if cost_id:
                cost_id = cost_id[0]
                vals['remaining_qty'] = cost_id.qty + quantity
                vals['value'] = cost_id[0].standard_price * quantity
                vals['unit_cost'] = cost_id[0].standard_price
        # handle case of out from location as out to customer
        # ToDO: handle fifo calculation based on each location in _run_fifo
        if self.cost_method in ('average', 'fifo'):
            fifo_vals = self._run_fifo(abs(quantity), company)
            vals['remaining_qty'] = fifo_vals.get('remaining_qty')
            # In case of AVCO, fix rounding issue of standard price when needed.
            if self.cost_method == 'average':
                currency = self.env.company.currency_id
                rounding_error = currency.round(self.standard_price * self.quantity_svl - self.value_svl)
                if rounding_error:
                    # If it is bigger than the (smallest number of the currency * quantity) / 2,
                    # then it isn't a rounding error but a stock valuation error, we shouldn't fix it under the hood ...
                    if abs(rounding_error) <= (abs(quantity) * currency.rounding) / 2:
                        vals['value'] += rounding_error
                        vals['rounding_adjustment'] = '\nRounding Adjustment: %s%s %s' % (
                            '+' if rounding_error > 0 else '',
                            float_repr(rounding_error, precision_digits=currency.decimal_places),
                            currency.symbol
                        )
            if self.cost_method == 'fifo':
                vals.update(fifo_vals)
        return vals

    def _prepare_out_svl_vals(self, quantity, company, lot=False,  location=False):
        self.ensure_one()

        # Custom logic for `avco_by_location`
        # if self.cost_method == 'avco_by_location':
        #     location = self.env.context.get('location_id')  # Make sure to pass this in context
        #     if location:
        #         matched_costs = [t for t in self.product_cost_history_summary_ids if t.location_id.id == location]
        #         if matched_costs:
        #             cost_record = matched_costs[0]
        #             quantity = -1 * quantity  # Quantity must be negative for out SVL
        #             value = cost_record.standard_price * quantity
        #             vals = {
        #                 'product_id': self.id,
        #                 'value': company.currency_id.round(value),
        #                 'unit_cost': cost_record.standard_price,
        #                 'quantity': quantity,
        #                 'remaining_qty': cost_record.qty + quantity,
        #                 'lot_id': lot.id if lot else False,
        #             }
        #             return vals
        # else:
        company_id = self.env.context.get('force_company', self.env.company.id)
        company = self.env['res.company'].browse(company_id)
        currency = company.currency_id
        # Quantity is negative for out valuation layers.
        quantity = -1 * quantity
        cost = self.standard_price
        if lot and lot.standard_price:
            cost = lot.standard_price
        vals = {
            'product_id': self.id,
            'value': currency.round(quantity * cost),
            'unit_cost': cost,
            'quantity': quantity,
            'lot_id': lot.id if lot else False,
        }
        fifo_vals = self._run_fifo(abs(quantity), company, lot=lot)
        vals['remaining_qty'] = fifo_vals.get('remaining_qty')
        # In case of AVCO, fix rounding issue of standard price when needed.
        if self.product_tmpl_id.cost_method == 'average' and not float_is_zero(self.quantity_svl,
                                                                               precision_rounding=self.uom_id.rounding):
            rounding_error = currency.round(
                (cost * self.quantity_svl - self.value_svl) * abs(quantity / self.quantity_svl)
            )

            # If it is bigger than the (smallest number of the currency * quantity) / 2,
            # then it isn't a rounding error but a stock valuation error, we shouldn't fix it under the hood ...
            threshold = currency.round(max((abs(quantity) * currency.rounding) / 2, currency.rounding))
            if rounding_error and abs(rounding_error) <= threshold:
                vals['value'] += rounding_error
                vals['rounding_adjustment'] = '\nRounding Adjustment: %s%s %s' % (
                    '+' if rounding_error > 0 else '',
                    float_repr(rounding_error, precision_digits=currency.decimal_places),
                    currency.symbol
                )
        if self.product_tmpl_id.cost_method == 'fifo':
            vals.update(fifo_vals)

        if self.cost_method == 'avco_by_location':
            if 'location_id' in self.env.context:
                location = self.env.context.get('location_id')  # Make sure to pass this in context
            if location:
                cost_id = [t for t in self.product_cost_ids if t.location_id == location]
                if cost_id:
                    cost_id = cost_id[0]
                    vals['remaining_qty'] = cost_id.qty + quantity
                    vals['value'] = cost_id[0].standard_price * quantity
                    vals['unit_cost'] = cost_id[0].standard_price

        # Fallback to native Odoo behavior
        return vals

    @api.depends('stock_valuation_layer_ids')
    @api.depends_context('to_date', 'company', 'force_location_id')
    def _compute_value_svl(self):
        """ inherit to add location based on context"""
        if 'force_location_id' not in self.env.context:
            super()._compute_value_svl()
        else:
            company_id = self.env.company.id
            domain = [
                ('product_id', 'in', self.ids),
                ('company_id', '=', company_id),
            ]
            if self.env.context.get('to_date'):
                to_date = fields.Datetime.to_datetime(self.env.context['to_date'])
                domain.append(('create_date', '<=', to_date))
            if self.env.context.get('force_location_id'):
                location = self.env['stock.location'].browse(self.env.context['force_location_id'])
                domain.append(('location_id', '=', location.id))
            groups = self.env['stock.valuation.layer'].read_group(domain, ['value:sum', 'quantity:sum'], ['product_id'])
            products = self.browse()
            for group in groups:
                product = self.browse(group['product_id'][0])
                product.value_svl = self.env.company.currency_id.round(group['value'])
                product.quantity_svl = group['quantity']
                products |= product
            remaining = (self - products)
            remaining.value_svl = 0
            remaining.quantity_svl = 0

    def _change_standard_price(self, new_price):
        """
        inherit to restrict update cost if cost method is avg by location
        """
        super(ProductProduct, self)._change_standard_price(new_price)
        if self.filtered(lambda p: p.cost_method == 'avco_by_location'):
            raise UserError(
                _("You cannot update the cost of a product. "
                  "Please use Stock Revaluation form."))

    def _run_fifo_vacuum(self, company=None):
        """
        disable function if cost avg by location
        """
        products = self.filtered(lambda x:x.cost_method != 'avco_by_location')
        return super(ProductProduct, products)._run_fifo_vacuum(company)

    def get_last_cost_history(self, location=False, to_date=False):
        """
        get last cost based on date and location
        """
        return self._get_new_cost(location=location, to_date=to_date)

    def _get_new_cost(self, location=False, to_date=False):
        domain = [('company_id', '=', self.env.company.id)]
        if location:
            domain.append(('location_id', '=', location.id))
        if to_date:
            domain.append(('date', '<=', to_date))
        cost_histories = self.product_cost_history_ids.filtered_domain(
            domain).sorted('date', reverse=True)
        return cost_histories[0].standard_price if cost_histories else 0.0

    def _get_old_cost(self, location=False, to_date=False):
        unit_cost = \
            sum(self.with_context(to_date=to_date).product_cost_ids.filtered(
                lambda line: line.location_id.id == location.id
                and line.company_id == location.company_id
                if location.company_id else self.env.company
            ).mapped('standard_price'))
        return unit_cost
