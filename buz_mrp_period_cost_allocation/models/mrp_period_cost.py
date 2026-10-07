import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, float_round

_logger = logging.getLogger(__name__)

class MrpPeriodCost(models.Model):
    _name = 'mrp.period.cost'
    _description = 'Manufacturing Period Cost Allocation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    date_from = fields.Date(string='From Date', required=True)
    date_to = fields.Date(string='To Date', required=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    allocation_base = fields.Selection([
        ('time', 'Actual Time (Duration)'),
        ('standard_cost', 'Standard Manufacturing Cost'),
        ('sale_price', 'Sale Price'),
        ('manual', 'Manual Cost')
    ], string='Allocation Base', required=True, default='time')
    
    inventory_only = fields.Boolean(
        string='Inventory Valuation Only', 
        default=True,
        help="If checked, creates only stock valuation layers without accounting entries (unless required by configuration)."
    )
    
    allow_accounting_entry = fields.Boolean(
        compute='_compute_allow_accounting_entry', 
        store=True,
        string='Allow Accounting Entry'
    )

    journal_id = fields.Many2one(
        'account.journal', string='Journal',
        domain=[('type', '=', 'general')],
        help="Journal used for accounting entries."
    )
    valuation_adjustment_account_id = fields.Many2one(
        'account.account', string='Variance Account',
        help="Counterpart account for inventory valuation adjustments (e.g., Cost Variance or Production Price Difference)."
    )
    
    # Costs
    actual_dl = fields.Float(string='Actual Direct Labor', digits='Product Price')
    actual_idl = fields.Float(string='Actual Indirect Labor', digits='Product Price')
    actual_oh = fields.Float(string='Actual Overhead', digits='Product Price')
    
    total_std_dl = fields.Float(string='Total Standard DL', compute='_compute_total_std_costs', store=True, digits='Product Price')
    total_std_idl = fields.Float(string='Total Standard IDL', compute='_compute_total_std_costs', store=True, digits='Product Price')
    total_std_oh = fields.Float(string='Total Standard OH', compute='_compute_total_std_costs', store=True, digits='Product Price')
    total_std_material = fields.Float(string='Total Standard Material', compute='_compute_total_std_costs', store=True, digits='Product Price')
    
    diff_dl = fields.Float(string='Diff DL', compute='_compute_diff_costs', store=True, digits='Product Price')
    diff_idl = fields.Float(string='Diff IDL', compute='_compute_diff_costs', store=True, digits='Product Price')
    diff_oh = fields.Float(string='Diff OH', compute='_compute_diff_costs', store=True, digits='Product Price')
    
    line_ids = fields.One2many('mrp.period.cost.line', 'period_id', string='Cost Lines')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_("From Date must not be after To Date."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('mrp.period.cost') or _('New')
        return super().create(vals_list)
        
    @api.depends('inventory_only')
    def _compute_allow_accounting_entry(self):
        for record in self:
            # Logic to check if any product category involved has real-time valuation could be complex here.
            # Simplified: If not inventory_only, we assume we might allow it.
            # The prompt says: "Accounting entries are disabled unless: User explicitly enables accounting mode"
            # It seems this field controls UI visibility or logic.
            record.allow_accounting_entry = not record.inventory_only

    @api.depends('line_ids.standard_dl', 'line_ids.standard_idl', 'line_ids.standard_oh', 'line_ids.standard_material')
    def _compute_total_std_costs(self):
        for record in self:
            record.total_std_dl = sum(record.line_ids.mapped('standard_dl'))
            record.total_std_idl = sum(record.line_ids.mapped('standard_idl'))
            record.total_std_oh = sum(record.line_ids.mapped('standard_oh'))
            record.total_std_material = sum(record.line_ids.mapped('standard_material'))

    @api.depends('actual_dl', 'actual_idl', 'actual_oh', 'total_std_dl', 'total_std_idl', 'total_std_oh')
    def _compute_diff_costs(self):
        for record in self:
            record.diff_dl = record.actual_dl - record.total_std_dl
            record.diff_idl = record.actual_idl - record.total_std_idl
            record.diff_oh = record.actual_oh - record.total_std_oh

    def action_load_mos(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_("Please define the period first."))
            
        # Clear existing lines
        self.line_ids.unlink()
        
        domain = [
            ('state', '=', 'done'),
            ('date_finished', '>=', self.date_from),
            ('date_finished', '<=', self.date_to),
            ('company_id', '=', self.company_id.id)
        ]
        mos = self.env['mrp.production'].search(domain)
        
        lines_vals = []
        for mo in mos:
            # Calculate standard DL/IDL/OH from workorders
            std_dl = 0.0
            std_idl = 0.0
            std_oh = 0.0
            total_duration = 0.0
            
            for wo in mo.workorder_ids:
                duration_min = wo.duration
                duration_hour = duration_min / 60.0
                total_duration += duration_min
                
                # Check for fields in workcenter
                wc = wo.workcenter_id
                if hasattr(wc, 'dl_per_hour'):
                     std_dl += duration_hour * wc.dl_per_hour
                if hasattr(wc, 'idl_per_hour'):
                     std_idl += duration_hour * wc.idl_per_hour
                if hasattr(wc, 'oh_per_hour'):
                     std_oh += duration_hour * wc.oh_per_hour
                     
                     
            # Calculate Standard Material Cost
            # Defined as total cost of components consumed
            std_material = 0.0
            for move in mo.move_raw_ids.filtered(lambda m: m.state == 'done'):
                # We use the value from the stock moves (quantity * price_unit)
                # It is safer/more accurate to check stock.valuation.layer if available but price_unit on done move is acceptable
                # Or sum(abs(svl.value) for svl in move.stock_valuation_layer_ids)
                # Fallback to price_unit
                std_material += sum(abs(svl.value) for svl in move.stock_valuation_layer_ids) or (move.quantity * move.price_unit)

            vals = {
                'mo_id': mo.id,
                'product_id': mo.product_id.id,
                'quantity_produced': mo.qty_produced,
                'total_duration': total_duration,
                'standard_dl': std_dl,
                'standard_idl': std_idl,
                'standard_oh': std_oh,
                'standard_material': std_material,
                'standard_total_cost': std_dl + std_idl + std_oh + std_material,
            }
            lines_vals.append((0, 0, vals))
            
        self.write({'line_ids': lines_vals})
        return True

    def action_preview_allocation(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No lines to allocate. Load MOs first."))
            
        total_base = 0.0
        # 1. Calculate total allocation base
        if self.allocation_base == 'time':
            total_base = sum(self.line_ids.mapped('total_duration'))
        elif self.allocation_base == 'standard_cost':
            total_base = sum(self.line_ids.mapped('standard_total_cost'))
        elif self.allocation_base == 'sale_price':
            total_base = sum(l.product_id.list_price * l.quantity_produced for l in self.line_ids)
        elif self.allocation_base == 'manual':
            total_base = sum(self.line_ids.mapped('manual_cost'))
            
        if float_is_zero(total_base, precision_digits=2):
             for line in self.line_ids:
                 line.write({
                     'allocation_weight': 0,
                     'allocated_dl': 0,
                     'allocated_idl': 0,
                     'allocated_oh': 0,
                     'final_total_cost': line.standard_total_cost,
                     'qty_on_hand': 0,
                     'inventory_ratio': 0,
                     'allocated_inventory_total': 0,
                     'allocated_period_expense': 0,
                 })
             return

        # 2. Allocate
        for line in self.line_ids:
            line_base = 0.0
            if self.allocation_base == 'time':
                line_base = line.total_duration
            elif self.allocation_base == 'standard_cost':
                line_base = line.standard_total_cost
            elif self.allocation_base == 'sale_price':
                line_base = line.product_id.list_price * line.quantity_produced
            elif self.allocation_base == 'manual':
                line_base = line.manual_cost
                
            weight = line_base / total_base
            
            allocated_dl = self.diff_dl * weight
            allocated_idl = self.diff_idl * weight
            allocated_oh = self.diff_oh * weight
            
            # Inventory Logic: Determine how much of the produced quantity is still in stock
            qty_on_hand = 0.0
            if line.mo_id.lot_producing_id:
                # If tracked by lot, check current quantity of that specific lot in internal locations
                quants = self.env['stock.quant'].search([
                    ('lot_id', '=', line.mo_id.lot_producing_id.id),
                    ('location_id.usage', '=', 'internal'),
                    ('company_id', '=', self.company_id.id)
                ])
                qty_on_hand = sum(quants.mapped('quantity'))
            else:
                # If NOT tracked by lot, check remaining quantity in the Stock Valuation Layers of the MO finished moves
                moves = line.mo_id.move_finished_ids.filtered(
                    lambda m: m.state == 'done' and m.product_id == line.product_id
                )
                # In Odoo 17, SVLs track 'remaining_qty' which is the quantity not yet consumed/sold
                qty_on_hand = sum(moves.mapped('stock_valuation_layer_ids.remaining_qty'))
            
            # Ensure we don't exceed produced qty (in case of weird stock moves)
            qty_on_hand = min(qty_on_hand, line.quantity_produced)
            qty_on_hand = max(0.0, qty_on_hand)
            
            inventory_ratio = 0.0
            if not float_is_zero(line.quantity_produced, precision_digits=2):
                inventory_ratio = qty_on_hand / line.quantity_produced
                
            total_allocated_variance = allocated_dl + allocated_idl + allocated_oh
            allocated_inventory_total = total_allocated_variance * inventory_ratio
            allocated_period_expense = total_allocated_variance - allocated_inventory_total

            line.write({
                'allocation_weight': weight * 100, # Display as percentage
                'allocated_dl': allocated_dl,
                'allocated_idl': allocated_idl,
                'allocated_oh': allocated_oh,
                'final_total_cost': line.standard_total_cost + allocated_dl + allocated_idl + allocated_oh,
                'qty_on_hand': qty_on_hand,
                'inventory_ratio': inventory_ratio * 100, # Display as %
                'allocated_inventory_total': allocated_inventory_total,
                'allocated_period_expense': allocated_period_expense,
            })
            
    def action_post(self):
        self.ensure_one()
        if self.state == 'posted':
            raise UserError(_("Already posted."))
        
        # Validation checks
        if not self.line_ids:
             raise UserError(_("No lines to post."))

        if not self.inventory_only:
            if not self.journal_id:
                raise UserError(_("Please select a Journal for accounting entries."))
            if not self.valuation_adjustment_account_id:
                raise UserError(_("Please select a Variance Account for accounting entries."))
             
        # Create SVLs. Only the share of the variance that is still in stock
        # (allocated_inventory_total) is capitalised; the share belonging to
        # goods already sold/issued (allocated_period_expense) is reporting only.
        for line in self.line_ids:
            adjustment_value = line.allocated_inventory_total
            if float_is_zero(adjustment_value, precision_digits=2):
                continue

            moves = line.mo_id.move_finished_ids.filtered(
                lambda m: m.state == 'done' and m.product_id == line.product_id and m.product_uom_qty > 0
            )

            total_qty_moved = sum(moves.mapped('product_uom_qty'))
            if total_qty_moved == 0:
                continue

            for move in moves:
                move_ratio = move.product_uom_qty / total_qty_moved
                move_adjustment = adjustment_value * move_ratio

                is_automated = move.product_id.valuation == 'real_time'

                # Like landed cost: link to the origin layer(s) and push the
                # value into their remaining_value so FIFO unit cost follows.
                base_layers = move.stock_valuation_layer_ids.filtered(lambda l: l.quantity > 0)
                svl_vals = {
                    'company_id': self.company_id.id,
                    'product_id': line.product_id.id,
                    'stock_move_id': move.id,
                    'stock_valuation_layer_id': base_layers[:1].id,
                    'quantity': 0,
                    'value': move_adjustment,
                    'description': _('Period Cost Allocation: %s - %s') % (self.name, line.mo_id.name),
                }

                svl = self.env['stock.valuation.layer'].create(svl_vals)
                distribution = self._add_remaining_value(base_layers, move_adjustment)
                self._record_allocations(svl, base_layers, distribution)

                if is_automated and not self.inventory_only:
                     self._create_accounting_entry(move, move_adjustment, svl)

        self.state = 'posted'
        return True

    @api.model
    def _add_remaining_value(self, base_layers, value):
        """Spread value over origin layers that still hold stock, by remaining_qty.

        Returns [(layer, amount, remaining_qty_at_post)] so a reversal can undo it.
        """
        in_stock = base_layers.filtered(lambda l: l.remaining_qty > 0)
        total_qty = sum(in_stock.mapped('remaining_qty'))
        if not total_qty:
            return []
        distribution = []
        for layer in in_stock:
            amount = value * layer.remaining_qty / total_qty
            distribution.append((layer, amount, layer.remaining_qty))
            layer.remaining_value += amount
        return distribution

    def _record_allocations(self, svl, base_layers, distribution):
        Alloc = self.env['mrp.period.cost.alloc']
        if not distribution:
            Alloc.create({
                'period_id': self.id, 'svl_id': svl.id,
                'base_layer_id': base_layers[:1].id, 'amount_remaining': 0.0,
            })
            return
        Alloc.create([{
            'period_id': self.id, 'svl_id': svl.id, 'base_layer_id': layer.id,
            'amount_remaining': amount, 'qty_at_post': qty,
        } for layer, amount, qty in distribution])

    def action_reverse_to_draft(self, reason):
        """Undo a posted period cost and put it back to draft.

        Blocked when any origin layer has been consumed since posting, because
        the adjustment would already be part of cost of goods sold.
        """
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_("Only a posted period cost can be reversed."))
        if not self.env.user.has_group('buz_mrp_period_cost_allocation.group_period_cost_reverse'):
            raise UserError(_("You are not allowed to reverse a posted period cost "
                              "(group 'Period Cost: Reverse Posted' required)."))
        if not (reason or '').strip():
            raise UserError(_("Please give a reason for the reversal."))

        record = self.sudo()
        allocs = self.env['mrp.period.cost.alloc'].sudo().search([
            ('period_id', '=', self.id), ('reversed', '=', False)])
        if not allocs and not self.env['mrp.period.cost.alloc'].sudo().search_count(
                [('period_id', '=', self.id)]):
            # Posted before allocations were recorded: layers cannot be traced.
            legacy = self.env['stock.valuation.layer'].sudo().search([
                ('description', 'like', 'Period Cost Allocation: %s - %%' % self.name)])
            if legacy:
                raise UserError(_(
                    "%(name)s was posted before allocation tracking existed, so its %(n)s "
                    "valuation layers cannot be reversed automatically. Ask accounting/IT to "
                    "correct it manually.", name=self.name, n=len(legacy)))
        consumed = allocs.filtered(lambda a: a._is_consumed())
        if consumed:
            raise UserError(_(
                "Cannot reverse %(name)s: stock from these layers has already been sold or issued, "
                "so the adjustment is part of cost of goods sold:\n%(layers)s",
                name=self.name,
                layers='\n'.join(sorted(set(
                    _('- %s (qty at post %s, now %s)') % (
                        a.base_layer_id.product_id.display_name,
                        a.qty_at_post, a.base_layer_id.remaining_qty)
                    for a in consumed)))))

        for alloc in allocs:
            alloc._reverse()
        record.write({'state': 'draft'})
        user = self.env.user
        # A user without an email would make message_post raise and roll the whole reversal back.
        self.message_post(
            body=_("Reversed and reset to draft by %(user)s. Reason: %(reason)s",
                   user=user.display_name, reason=reason),
            author_id=user.partner_id.id,
            email_from=user.email_formatted or self.env.company.email_formatted
            or 'noreply@localhost')
        return True

    def action_cancel(self):
        if any(rec.state == 'posted' for rec in self):
            raise UserError(_("A posted period cost cannot be cancelled: its valuation adjustments are already booked."))
        self.write({'state': 'cancel'})

    @api.ondelete(at_uninstall=False)
    def _unlink_except_posted(self):
        if any(rec.state == 'posted' for rec in self):
            raise UserError(_("A posted period cost cannot be deleted: its valuation adjustments are already booked."))

    def action_draft(self):
        self.write({'state': 'draft'})
        self.line_ids._check_mo_not_allocated()

    def _create_accounting_entry(self, move, value, svl):
        """Create a journal entry for the valuation adjustment."""
        product = move.product_id
        accounts = product.product_tmpl_id.get_product_accounts()
        debit_account_id = accounts.get('stock_valuation')
        
        # Use configured variance account from the period cost record
        credit_account_id = self.valuation_adjustment_account_id
        journal_id = self.journal_id or accounts.get('stock_journal')
        
        if not debit_account_id or not credit_account_id:
             _logger.warning("Missing accounts for product %s. Valuation Adjustment skipped.", product.name)
             return

        move_vals = {
            'journal_id': journal_id.id,
            'date': fields.Date.today(),
            'ref': self.name,
            'move_type': 'entry',
            'stock_valuation_layer_ids': [(4, svl.id)], # Link SVL to AM
            'line_ids': [
                (0, 0, {
                    'name': _('Valuation Adjustment: %s') % product.name,
                    'account_id': debit_account_id.id,
                    'debit': value if value > 0 else 0,
                    'credit': -value if value < 0 else 0,
                    'product_id': product.id,
                }),
                (0, 0, {
                    'name': _('Cost Variance: %s') % product.name,
                    'account_id': credit_account_id.id,
                    'debit': -value if value < 0 else 0,
                    'credit': value if value > 0 else 0,
                     'product_id': product.id,
                })
            ]
        }
        
        am = self.env['account.move'].create(move_vals)
        am.action_post()
        svl.write({'account_move_id': am.id})


class MrpPeriodCostLine(models.Model):
    _name = 'mrp.period.cost.line'
    _description = 'Manufacturing Period Cost Line'
    
    period_id = fields.Many2one('mrp.period.cost', string='Period Cost', required=True, ondelete='cascade')
    mo_id = fields.Many2one('mrp.production', string='Manufacturing Order', required=True, readonly=True)
    product_id = fields.Many2one('product.product', string='Product', related='mo_id.product_id', store=True)
    
    quantity_produced = fields.Float(string='Qty Produced', readonly=True, digits='Product Unit of Measure')
    total_duration = fields.Float(string='Total Duration (Min)', readonly=True, help="Total duration of work orders in minutes")
    
    standard_dl = fields.Float(string='Std DL', readonly=True, digits='Product Price')
    standard_idl = fields.Float(string='Std IDL', readonly=True, digits='Product Price')
    standard_oh = fields.Float(string='Std OH', readonly=True, digits='Product Price')
    standard_material = fields.Float(string='Std Material', readonly=True, digits='Product Price')
    standard_total_cost = fields.Float(string='Std Total', readonly=True, digits='Product Price')
    
    allocation_weight = fields.Float(string='Weight (%)', readonly=True, digits=(12, 4))
    
    manual_cost = fields.Float(string='Manual Cost', digits='Product Price')
    
    allocated_dl = fields.Float(string='Alloc DL', readonly=True, digits='Product Price')
    allocated_idl = fields.Float(string='Alloc IDL', readonly=True, digits='Product Price')
    allocated_oh = fields.Float(string='Alloc OH', readonly=True, digits='Product Price')
    
    final_total_cost = fields.Float(string='Final Cost', readonly=True, digits='Product Price')
    
    # Inventory & Variance Split
    qty_on_hand = fields.Float(string='On Hand', readonly=True, digits='Product Unit of Measure', help="Quantity remaining in stock (tracked by Lot)")
    qty_sold = fields.Float(string='Sold/Issued', compute='_compute_qty_sold', store=True, digits='Product Unit of Measure')
    inventory_ratio = fields.Float(string='Inv Ratio (%)', readonly=True, digits=(12, 2))
    
    allocated_inventory_total = fields.Float(string='Inv Adjustment', readonly=True, digits='Product Price', help="Variance allocated to remaining inventory")
    allocated_period_expense = fields.Float(string='Period Expense', readonly=True, digits='Product Price', help="Variance allocated to Sold/Issued goods")

    @api.constrains('mo_id', 'period_id')
    def _check_mo_not_allocated(self):
        """An MO can sit in only one non-cancelled period cost."""
        for line in self:
            if line.period_id.state == 'cancel':
                continue
            other = self.search([
                ('mo_id', '=', line.mo_id.id),
                ('id', '!=', line.id),
                ('period_id', '!=', line.period_id.id),
                ('period_id.state', '!=', 'cancel'),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    "Manufacturing Order %(mo)s is already allocated in %(period)s.",
                    mo=line.mo_id.display_name, period=other.period_id.display_name))

    @api.depends('quantity_produced', 'qty_on_hand')
    def _compute_qty_sold(self):
        for line in self:
            line.qty_sold = max(0, line.quantity_produced - line.qty_on_hand)


class MrpPeriodCostAlloc(models.Model):
    """Where a posted period cost put its value, so it can be reversed exactly."""
    _name = 'mrp.period.cost.alloc'
    _description = 'Manufacturing Period Cost Layer Allocation'

    period_id = fields.Many2one('mrp.period.cost', required=True, ondelete='restrict', index=True)
    svl_id = fields.Many2one('stock.valuation.layer', string='Adjustment Layer', required=True, ondelete='restrict')
    base_layer_id = fields.Many2one('stock.valuation.layer', string='Origin Layer', ondelete='restrict')
    amount_remaining = fields.Float(help="Value added to the origin layer's remaining_value.",
                                    digits='Product Price')
    qty_at_post = fields.Float(help="Origin layer remaining_qty when posted.", digits='Product Unit of Measure')
    reversed = fields.Boolean(default=False)
    reversal_svl_id = fields.Many2one('stock.valuation.layer', string='Reversal Layer', ondelete='restrict')

    def _is_consumed(self):
        self.ensure_one()
        if not self.amount_remaining:
            return False
        rounding = self.base_layer_id.product_id.uom_id.rounding
        return float_compare(self.base_layer_id.remaining_qty, self.qty_at_post,
                             precision_rounding=rounding) < 0

    def _reverse(self):
        self.ensure_one()
        svl = self.svl_id
        vals = {
            'company_id': svl.company_id.id,
            'product_id': svl.product_id.id,
            'stock_move_id': svl.stock_move_id.id,
            'stock_valuation_layer_id': svl.stock_valuation_layer_id.id,
            'quantity': 0,
            'value': -svl.value,
            'description': _('Reversal of: %s') % svl.description,
        }
        # Provided by the FIFO modules on prod; keep the reversal in the same
        # accounting period as the layer it cancels.
        if 'accounting_date' in svl._fields:
            vals['accounting_date'] = svl.accounting_date
        rev = self.env['stock.valuation.layer'].create(vals)
        if self.amount_remaining:
            self.base_layer_id.remaining_value -= self.amount_remaining
        if svl.account_move_id:
            reversal = svl.account_move_id._reverse_moves(
                default_values_list=[{'ref': _('Reversal of %s') % svl.account_move_id.ref}],
                cancel=True)
            rev.account_move_id = reversal.id
        self.write({'reversed': True, 'reversal_svl_id': rev.id})
