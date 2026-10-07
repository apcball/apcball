import logging
from datetime import datetime, time
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
    adjustment_date = fields.Date(
        string='Adjustment Date', compute='_compute_adjustment_date', store=True,
        readonly=False, precompute=True, required=True, copy=False,
        help="Period close date. The cost adjustment layers (accounting date) and the "
             "journal entries are dated here. Defaults to To Date.")
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

    @api.depends('date_to')
    def _compute_adjustment_date(self):
        for rec in self:
            rec.adjustment_date = rec.date_to

    @api.constrains('date_from', 'date_to', 'adjustment_date')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_("From Date must not be after To Date."))
            if rec.date_from and rec.adjustment_date and rec.adjustment_date < rec.date_from:
                raise ValidationError(_("Adjustment Date must not be before From Date."))

    def _lock_date_warning(self):
        """Text when adjustment_date falls in a locked accounting period, else ''."""
        self.ensure_one()
        company = self.company_id
        getter = getattr(company, '_get_user_fiscal_lock_date', None)
        lock = getter() if getter else company.fiscalyear_lock_date
        lock = max([d for d in (lock, company.tax_lock_date) if d] or [False])
        if lock and self.adjustment_date and self.adjustment_date <= lock:
            return _("Adjustment Date %(date)s is in a locked accounting period (locked until %(lock)s). "
                     "Valuation layers will still be posted, but a journal entry dated there will be refused.",
                     date=self.adjustment_date, lock=lock)
        return ''

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
            # Stock still held (any warehouse) by the MO's finished layers and
            # their transfer chain. Transfers are not consumption.
            moves = line.mo_id.move_finished_ids.filtered(
                lambda m: m.state == 'done' and m.product_id == line.product_id
            )
            target_layers = self.env['stock.valuation.layer']
            for move in moves:
                target_layers |= self._get_target_layers(move)[1]
            if target_layers:
                qty_on_hand = sum(target_layers.mapped('remaining_qty'))
            elif line.mo_id.lot_producing_id:
                # No valuation layers to follow: fall back to the lot's internal quants
                quants = self.env['stock.quant'].search([
                    ('lot_id', '=', line.mo_id.lot_producing_id.id),
                    ('location_id.usage', '=', 'internal'),
                    ('company_id', '=', self.company_id.id)
                ])
                qty_on_hand = sum(quants.mapped('quantity'))
            else:
                qty_on_hand = 0.0

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
            
    def action_post_wizard(self):
        """Refresh the preview, then ask the user to confirm in a Thai checklist wizard."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Only a draft period cost can be posted."))
        self.action_preview_allocation()
        wizard = self.env['mrp.period.cost.post.wizard'].create({'period_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Confirm Post'),
            'res_model': 'mrp.period.cost.post.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

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
            # Split by stock still held per move (incl. transferred stock), so
            # nothing is lost when a move's own base layer is already exhausted.
            targets = {move: self._get_target_layers(move) for move in moves}
            held = {move: sum(t[1].mapped('remaining_qty')) for move, t in targets.items()}
            total_held = sum(held.values())
            if total_held <= 0:
                _logger.warning("Period cost %s: no stock held for MO %s, variance not capitalised.",
                                self.name, line.mo_id.name)
                continue

            remaining_value = adjustment_value
            last_move = [m for m in moves if held[m] > 0][-1]
            for move in moves:
                if held[move] <= 0:
                    continue
                if move == last_move:
                    move_adjustment = remaining_value
                else:
                    move_adjustment = float_round(adjustment_value * held[move] / total_held, precision_digits=2)
                    remaining_value -= move_adjustment
                origin_layers, target_layers = targets[move]
                self._post_move_adjustment(line, move, move_adjustment, origin_layers, target_layers)

        self.state = 'posted'
        return True

    def _accounting_datetime(self):
        """End of the adjustment (period close) date, so the layer falls in the month it belongs to."""
        return datetime.combine(self.adjustment_date, time(23, 59, 59))

    @api.model
    def _get_target_layers(self, move):
        """Return (origin_layers, layers that may still hold the move's stock).

        With stock_fifo_by_location, an inter-warehouse transfer consumes the
        origin layer's remaining_qty but the goods live on in position layers
        linked through origin_valuation_layer_id; follow that chain (same idea
        as stock_landed_cost._get_landed_cost_targets). Without it, only the
        move's own layers.
        """
        Layer = self.env['stock.valuation.layer']
        base_layers = move.stock_valuation_layer_ids.filtered(lambda l: l.quantity > 0)
        if 'origin_valuation_layer_id' not in Layer._fields:
            return base_layers, base_layers
        origin_layers = base_layers.mapped('origin_valuation_layer_id') | base_layers.filtered(
            lambda l: not l.origin_valuation_layer_id)
        chain_ids = set(origin_layers.ids)
        chain_ids.update(Layer.search([('origin_valuation_layer_id', 'in', list(chain_ids))]).ids)
        position_layers = Layer.search([
            ('origin_valuation_layer_id', 'in', list(chain_ids)),
            ('quantity', '>', 0),
        ])
        return origin_layers, position_layers | origin_layers | base_layers

    def _post_move_adjustment(self, line, move, value, origin_layers, target_layers):
        """Capitalise `value` on the stock still held, one adjustment layer per receiving layer.

        Each qty-0 layer points (stock_valuation_layer_id) at the layer whose
        remaining_value it topped up and carries that layer's warehouse. The FIFO
        replay applies a qty-0 layer to its target inside the target's warehouse
        pool, so a layer pointing at another warehouse's layer would be ignored
        and the recalculation wizard would wipe the uplift.
        """
        Layer = self.env['stock.valuation.layer']
        distribution = self._add_remaining_value(target_layers, value)
        if not distribution:
            return
        origin_layer = origin_layers[:1]
        is_automated = move.product_id.valuation == 'real_time'
        for layer, amount, qty in distribution:
            svl_vals = {
                'company_id': self.company_id.id,
                'product_id': line.product_id.id,
                'stock_move_id': move.id,
                'stock_valuation_layer_id': layer.id,
                'quantity': 0,
                'value': amount,
                'description': _('Period Cost Allocation: %s - %s') % (self.name, line.mo_id.name),
            }
            if 'warehouse_id' in Layer._fields and layer.warehouse_id:
                svl_vals['warehouse_id'] = layer.warehouse_id.id
            if 'origin_valuation_layer_id' in Layer._fields and origin_layer:
                svl_vals['origin_valuation_layer_id'] = origin_layer.id
            if 'accounting_date' in Layer._fields:
                svl_vals['accounting_date'] = self._accounting_datetime()
            svl = Layer.create(svl_vals)
            self._record_allocations(svl, [(layer, amount, qty)], origin_layer)
            if is_automated and not self.inventory_only:
                self._create_accounting_entry(move, amount, svl)

    @api.model
    def _add_remaining_value(self, layers, value):
        """Spread value over layers that still hold stock, by remaining_qty.

        Returns [(layer, amount, remaining_qty_at_post)] so a reversal can undo it.
        The amounts add up exactly to `value`.
        """
        in_stock = layers.filtered(lambda l: l.remaining_qty > 0)
        total_qty = sum(in_stock.mapped('remaining_qty'))
        if not total_qty:
            return []
        distribution = []
        left = value
        for i, layer in enumerate(in_stock):
            if i == len(in_stock) - 1:
                amount = left
            else:
                amount = float_round(value * layer.remaining_qty / total_qty, precision_digits=2)
                left -= amount
            distribution.append((layer, amount, layer.remaining_qty))
            layer.remaining_value += amount
        return distribution

    def _record_allocations(self, svl, items, origin_layer=None):
        """Record where `items` [(layer, amount, qty)] went; the cost origin gets the total once."""
        Alloc = self.env['mrp.period.cost.alloc']
        total = sum(a for _l, a, _q in items)
        track_origin = origin_layer and 'origin_remaining_value' in origin_layer._fields
        if track_origin:
            origin_layer.origin_remaining_value += total
        vals = []
        for i, (layer, amount, qty) in enumerate(items):
            vals.append({
                'period_id': self.id, 'svl_id': svl.id, 'base_layer_id': layer.id,
                'amount_remaining': amount, 'qty_at_post': qty,
                'origin_layer_id': origin_layer.id if track_origin and i == 0 else False,
                'origin_amount': total if track_origin and i == 0 else 0.0,
            })
        Alloc.create(vals)

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
            'date': self.adjustment_date,
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
    origin_layer_id = fields.Many2one('stock.valuation.layer', string='Cost Origin Layer', ondelete='restrict',
                                      help="Layer whose origin_remaining_value received origin_amount.")
    origin_amount = fields.Float(digits='Product Price')
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
        for fname in ('warehouse_id', 'origin_valuation_layer_id'):
            if fname in svl._fields and svl[fname]:
                vals[fname] = svl[fname].id
        rev = self.env['stock.valuation.layer'].create(vals)
        if self.origin_amount and self.origin_layer_id:
            self.origin_layer_id.origin_remaining_value -= self.origin_amount
        if self.amount_remaining:
            self.base_layer_id.remaining_value -= self.amount_remaining
        if svl.account_move_id:
            reversal = svl.account_move_id._reverse_moves(
                default_values_list=[{'ref': _('Reversal of %s') % svl.account_move_id.ref}],
                cancel=True)
            rev.account_move_id = reversal.id
        self.write({'reversed': True, 'reversal_svl_id': rev.id})
