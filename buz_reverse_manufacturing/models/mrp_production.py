# Part of buz addons for Mogen Co. See LICENSE file.
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools import float_is_zero, float_round

from .mrp_bom import ALLOCATION_METHODS


class MrpProduction(models.Model):
    """Reverse Manufacturing Order (RMO) on top of mrp.production.

    A reverse order consumes ONE finished product (the input) and produces
    the recovered components listed on its recovery lines. All finished
    moves are by-product style moves (no finished move for ``product_id``
    itself), so the standard mrp_account cost-share machinery and the whole
    work-order framework (tablet, labor, OEE) are reused unchanged.
    """

    _inherit = 'mrp.production'

    is_reverse = fields.Boolean(
        string='Reverse Manufacturing',
        readonly=True,
        index=True,
        help='Technical: this order disassembles its product into the '
             'recovered components of its recovery lines.',
    )
    allocation_method = fields.Selection(
        ALLOCATION_METHODS,
        string='Cost Allocation Method',
        default='bom_cost',
        tracking=True,
        help='How the total recoverable cost (input product value + labor '
             '+ operations + extra cost) is distributed across the '
             'recovered components.',
    )
    recovery_line_ids = fields.One2many(
        'buz.reverse.recovery.line',
        'production_id',
        string='Recovered Components',
        copy=False,
    )
    recovery_line_count = fields.Integer(
        compute='_compute_reverse_stats')
    total_input_cost = fields.Monetary(
        string='Input Cost',
        compute='_compute_reverse_stats',
        currency_field='company_currency_id',
        help='Value of the consumed input product (valuation layers once '
             'done, standard price estimate before).',
    )
    total_labor_cost = fields.Monetary(
        string='Labor / Operation Cost',
        compute='_compute_reverse_stats',
        currency_field='company_currency_id',
    )
    total_recovered_value = fields.Monetary(
        string='Recovered Value',
        compute='_compute_reverse_stats',
        currency_field='company_currency_id',
    )
    total_scrap_value = fields.Monetary(
        string='Scrap Value',
        compute='_compute_reverse_stats',
        currency_field='company_currency_id',
    )
    recovery_rate_percent = fields.Float(
        string='Recovery Rate %',
        compute='_compute_reverse_stats',
        digits=(5, 2),
        help='Total actual recovered quantity / total expected quantity.',
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id')

    # ------------------------------------------------------------------
    # CRUD / defaults
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_reverse') and not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'buz.reverse.manufacturing.order') or _('New')
        productions = super().create(vals_list)
        # Programmatic creation skips onchanges: make sure reverse orders
        # get their recovery lines and finished moves from the BOM.
        for production in productions.filtered(
                lambda p: p.is_reverse and p.bom_id
                and not p.recovery_line_ids):
            production.recovery_line_ids = [
                Command.create(vals)
                for vals in production._prepare_recovery_line_vals()
            ]
            production._create_update_move_finished()
        return productions

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('recovery_line_ids', 'recovery_line_ids.actual_qty',
                 'recovery_line_ids.expected_qty', 'move_raw_ids.state',
                 'move_finished_ids.state', 'workorder_ids.duration',
                 'extra_cost')
    def _compute_reverse_stats(self):
        for order in self:
            lines = order.recovery_line_ids
            order.recovery_line_count = len(lines)
            if not order.is_reverse:
                order.total_input_cost = 0.0
                order.total_labor_cost = 0.0
                order.total_recovered_value = 0.0
                order.total_scrap_value = 0.0
                order.recovery_rate_percent = 0.0
                continue
            order.total_input_cost = order._get_reverse_input_cost()
            order.total_labor_cost = sum(
                wo._cal_cost() for wo in order.workorder_ids)
            order.total_recovered_value = sum(
                lines.mapped('final_cost')) or sum(
                lines.mapped('calculated_cost'))
            order.total_scrap_value = sum(
                line.scrap_qty * line.product_id.standard_price
                for line in lines)
            expected = sum(lines.mapped('expected_qty'))
            actual = sum(lines.mapped('actual_qty'))
            order.recovery_rate_percent = (
                actual / expected * 100.0 if expected else 0.0)

    def _get_reverse_input_cost(self):
        """Value of the consumed input product.

        Uses the real valuation layers of the raw moves once they are
        done (actual FIFO/AVCO cost); falls back to the standard price
        estimate while the order is in progress.
        """
        self.ensure_one()
        raw_moves = self.move_raw_ids.filtered(lambda m: m.state != 'cancel')
        layers = raw_moves.sudo().stock_valuation_layer_ids
        if layers:
            return -sum(layers.mapped('value'))
        return self.product_id.standard_price * self.product_qty

    # ------------------------------------------------------------------
    # Move generation (the core trick)
    # ------------------------------------------------------------------

    def _get_moves_raw_values(self):
        """Reverse orders consume the single input product, not BOM lines."""
        reverse_orders = self.filtered('is_reverse')
        moves = super(MrpProduction, self - reverse_orders)._get_moves_raw_values()
        for production in reverse_orders:
            moves.append(production._get_move_raw_values(
                production.product_id,
                production.product_qty,
                production.product_uom_id,
            ))
        return moves

    def _get_moves_finished_values(self):
        """Reverse orders produce their recovery lines as by-product style
        moves. No finished move is created for ``product_id`` itself, so
        every output move carries a ``cost_share`` and the whole cost of
        the order is distributed across the recovered components."""
        reverse_orders = self.filtered('is_reverse')
        moves = super(MrpProduction, self - reverse_orders)._get_moves_finished_values()
        for production in reverse_orders:
            for line in production.recovery_line_ids:
                if float_is_zero(line.actual_qty,
                                 precision_rounding=line.product_uom_id.rounding):
                    continue
                vals = production._get_move_finished_values(
                    line.product_id.id,
                    line.actual_qty,
                    line.product_uom_id.id,
                    cost_share=line.allocation_percent,
                )
                vals.update({
                    'location_dest_id': line.destination_location_id.id,
                    'reverse_recovery_line_id': line.id,
                })
                moves.append(vals)
        return moves

    def _create_update_move_finished(self):
        """Core keys the update on ``byproduct_id`` and on the main
        finished move; reverse orders key on the recovery line instead."""
        reverse_orders = self.filtered('is_reverse')
        super(MrpProduction, self - reverse_orders)._create_update_move_finished()
        for production in reverse_orders:
            commands = []
            moves_by_line = {
                move.reverse_recovery_line_id.id: move
                for move in production.move_finished_ids
                if move.reverse_recovery_line_id
            }
            seen_line_ids = set()
            for vals in production._get_moves_finished_values():
                line_id = vals.get('reverse_recovery_line_id')
                seen_line_ids.add(line_id)
                if line_id in moves_by_line:
                    commands.append(
                        Command.update(moves_by_line[line_id].id, vals))
                else:
                    commands.append(Command.create(vals))
            # Drop moves whose recovery line disappeared or fell to zero.
            for line_id, move in moves_by_line.items():
                if line_id not in seen_line_ids and move.state not in ('done', 'cancel'):
                    commands.append(Command.unlink(move.id))
            # Every finished move on a reverse order must carry a recovery
            # line. Orphans happen when core's own create() flow calls this
            # method before recovery_line_ids has real ids (NewId can't be
            # assigned to reverse_recovery_line_id, so the move ends up
            # unlinked and invisible to the cleanup above): drop them too.
            orphan_moves = production.move_finished_ids.filtered(
                lambda m: not m.reverse_recovery_line_id
                and m.state not in ('done', 'cancel'))
            for move in orphan_moves:
                commands.append(Command.unlink(move.id))
            production.move_finished_ids = commands
            for move in production.move_finished_ids:
                if move.reverse_recovery_line_id:
                    move.reverse_recovery_line_id.move_id = move

    @api.depends('workorder_ids.state', 'move_finished_ids',
                 'move_finished_ids.quantity', 'move_raw_ids.quantity')
    def _get_produced_qty(self):
        """For reverse orders the produced quantity mirrors the consumed
        input quantity (there is no finished move for ``product_id``)."""
        reverse_orders = self.filtered('is_reverse')
        res = super(MrpProduction, self - reverse_orders)._get_produced_qty()
        for production in reverse_orders:
            done_raw = production.move_raw_ids.filtered(
                lambda m: m.state == 'done' and m.picked
                and m.product_id == production.product_id)
            production.qty_produced = sum(done_raw.mapped('quantity'))
        return res

    def _set_quantities(self):
        """Core generates a *new* lot for tracked products here — wrong
        direction for a reverse order (we consume an existing lot, we do
        not produce the input product). Set the producing quantity and let
        the raw move carry the input lot through normal reservation."""
        self.ensure_one()
        if not self.is_reverse:
            return super()._set_quantities()
        self.qty_producing = self.product_qty - self.qty_produced
        self._set_qty_producing()
        return True

    def _split_productions(self, amounts=False, cancel_remaining_qty=False,
                           set_consumed_qty=False):
        if any(p.is_reverse for p in self):
            raise UserError(_(
                'Reverse Manufacturing Orders cannot be split into '
                'backorders. Process the full input quantity, or cancel '
                'and create an order for a smaller quantity.'))
        return super()._split_productions(
            amounts=amounts, cancel_remaining_qty=cancel_remaining_qty,
            set_consumed_qty=set_consumed_qty)

    # ------------------------------------------------------------------
    # Recovery line generation
    # ------------------------------------------------------------------

    @api.depends('product_id', 'picking_type_id', 'company_id')
    def _compute_bom_id(self):
        """Core's ``_bom_find`` defaults to a non-reverse BOM: our
        ``_bom_find_domain`` override excludes ``type='reverse'`` whenever
        ``bom_type`` isn't passed explicitly (see mrp_bom.py), and core
        never passes it. Left alone, a Reverse Manufacturing Order would
        never auto-select its reverse BOM even when one exists. Compute it
        ourselves for reverse orders; let core handle everything else."""
        reverse_orders = self.filtered('is_reverse')
        super(MrpProduction, self - reverse_orders)._compute_bom_id()
        for production in reverse_orders:
            if (production.bom_id
                    and production.bom_id.type == 'reverse'
                    and production.bom_id.product_tmpl_id == production.product_tmpl_id
                    and (not production.bom_id.product_id
                         or production.bom_id.product_id == production.product_id)):
                continue
            if not production.product_id:
                production.bom_id = False
                continue
            bom = self.env['mrp.bom']._bom_find(
                production.product_id,
                picking_type=production.picking_type_id,
                company_id=production.company_id.id,
                bom_type='reverse')[production.product_id]
            production.bom_id = bom.id or False

    @api.onchange('product_id', 'move_raw_ids')
    def _onchange_product_id(self):
        """Core strips any raw move whose product equals the product to
        produce and warns (guards against self-referencing BOMs). Reverse
        orders legitimately consume ``product_id`` itself as the single
        input move (see ``_get_moves_raw_values``): skip the core check
        for them so the raw move survives the onchange."""
        if self.is_reverse:
            return
        return super()._onchange_product_id()

    @api.onchange('bom_id', 'product_qty', 'product_uom_id')
    def _onchange_bom_id_reverse(self):
        if self.is_reverse and self.bom_id and self.state == 'draft':
            self.allocation_method = self.bom_id.allocation_method or 'bom_cost'
            self.recovery_line_ids = [Command.clear()] + [
                Command.create(vals)
                for vals in self._prepare_recovery_line_vals()
            ]

    def _prepare_recovery_line_vals(self):
        """Explode the reverse BOM into recovery line values."""
        self.ensure_one()
        vals_list = []
        if not self.bom_id or self.bom_id.type != 'reverse':
            return vals_list
        factor = self.product_uom_id._compute_quantity(
            self.product_qty, self.bom_id.product_uom_id) / self.bom_id.product_qty
        default_dest = self.location_dest_id
        for bom_line in self.bom_id.bom_line_ids:
            expected = bom_line.product_qty * factor
            recovery = bom_line.recovery_percent or 100.0
            vals_list.append({
                'sequence': bom_line.sequence,
                'bom_line_id': bom_line.id,
                'product_id': bom_line.product_id.id,
                'product_uom_id': bom_line.product_uom_id.id,
                'expected_qty': expected,
                'recovery_percent': recovery,
                'actual_qty': expected * recovery / 100.0,
                'scrap_policy': bom_line.scrap_policy or 'auto',
                'destination_location_id': (
                    bom_line.dest_location_id.id or default_dest.id),
                'manual_percent': bom_line.allocation_percent,
            })
        return vals_list

    def action_generate_recovery_lines(self):
        """Button: (re)generate recovery lines from the reverse BOM."""
        for production in self:
            if not production.is_reverse or production.state != 'draft':
                continue
            production.recovery_line_ids.unlink()
            production.recovery_line_ids = [
                Command.create(vals)
                for vals in production._prepare_recovery_line_vals()
            ]
        return True

    def action_confirm(self):
        for production in self.filtered('is_reverse'):
            if not production.recovery_line_ids:
                production.recovery_line_ids = [
                    Command.create(vals)
                    for vals in production._prepare_recovery_line_vals()
                ]
            if not production.recovery_line_ids:
                raise UserError(_(
                    'Reverse order %s has no recovered components. Select '
                    'a reverse BOM or add recovery lines manually.')
                    % production.name)
            # Recovery lines may have been added/edited after create():
            # core action_confirm does not regenerate finished moves when
            # raw moves already exist, so sync them here.
            production._create_update_move_finished()
        return super().action_confirm()

    def action_cancel(self):
        res = super().action_cancel()
        # Core derives `state` from move states (see mrp core
        # `_compute_state`), and `all()` over an empty `move_finished_ids`
        # is vacuously True. Reverse orders routinely have zero finished
        # moves at cancel time (no recovery lines generated yet, or none
        # survived), so the compute either gets stuck on 'draft' (no
        # moves at all) or misfires to 'done' (raw move cancelled, no
        # finished moves to gate against). Cancel here is unconditional —
        # core would already have refused above if it weren't allowed —
        # so force the state directly for every reverse order involved.
        reverse_orders = self.filtered('is_reverse')
        if reverse_orders:
            reverse_orders.write({'state': 'cancel'})
        return res

    # ------------------------------------------------------------------
    # Allocation engine
    # ------------------------------------------------------------------

    def _compute_recovery_allocations(self):
        """Write ``allocation_percent`` on every recovery line with a
        positive actual quantity so that the lines add up to exactly
        100.00 (%). The last line absorbs the rounding residual."""
        for production in self:
            if not production.is_reverse:
                continue
            method = production.allocation_method or 'bom_cost'
            lines = production.recovery_line_ids.filtered(
                lambda l: not float_is_zero(
                    l.actual_qty,
                    precision_rounding=l.product_uom_id.rounding))
            production.recovery_line_ids.filtered(
                lambda l: l not in lines).allocation_percent = 0.0
            if not lines:
                continue
            bases = {line.id: line._get_allocation_basis(method)
                     for line in lines}
            total = sum(bases.values())
            if float_is_zero(total, precision_digits=4):
                raise ValidationError(_(
                    'Cannot allocate costs on %(order)s: allocation method '
                    '"%(method)s" gives a zero total basis. Fill in the '
                    'relevant values (cost, percentage, quantity, weight '
                    'or amount) on the recovery lines.',
                    order=production.name,
                    method=dict(ALLOCATION_METHODS)[method]))
            if method == 'percentage':
                if float_round(total - 100.0, precision_digits=2):
                    raise ValidationError(_(
                        'The manual percentages on %s must add up to 100.')
                        % production.name)
            remainder = 100.0
            for line in lines[:-1]:
                pct = float_round(bases[line.id] / total * 100.0,
                                  precision_digits=2)
                line.allocation_percent = pct
                remainder -= pct
            lines[-1].allocation_percent = float_round(
                remainder, precision_digits=2)

    def _validate_recovery_lines(self):
        """Business checks before a reverse order can be marked done."""
        for production in self:
            lines = production.recovery_line_ids
            active_lines = lines.filtered(
                lambda l: not float_is_zero(
                    l.actual_qty,
                    precision_rounding=l.product_uom_id.rounding))
            if not active_lines:
                raise UserError(_(
                    'Nothing is recovered on %s: at least one recovery '
                    'line needs a positive actual quantity.')
                    % production.name)
            total = sum(active_lines.mapped('allocation_percent'))
            if float_round(total - 100.0, precision_digits=2):
                raise UserError(_(
                    'The cost allocation of %(order)s adds up to '
                    '%(total).2f%% instead of 100%%.',
                    order=production.name, total=total))
            for line in active_lines:
                if line.destination_location_id.usage != 'internal':
                    raise UserError(_(
                        '%s: the destination location must be internal.')
                        % line.product_id.display_name)
                if line.tracking != 'none' and not line.lot_id:
                    raise UserError(_(
                        '%s is tracked: assign a Lot/Serial on its '
                        'recovery line before marking the order done.')
                        % line.product_id.display_name)
                if (line.tracking == 'serial'
                        and float_round(line.actual_qty - 1.0,
                                        precision_digits=2) > 0):
                    raise UserError(_(
                        '%s is tracked by unique serial number: one '
                        'recovery line per unit (actual quantity 1) is '
                        'required.') % line.product_id.display_name)

    # ------------------------------------------------------------------
    # Mark done: allocation -> cost_share sync -> lots -> scraps
    # ------------------------------------------------------------------

    def button_mark_done(self):
        reverse_orders = self.filtered(
            lambda p: p.is_reverse and p.state not in ('done', 'cancel'))
        for production in reverse_orders:
            production._compute_recovery_allocations()
            production._validate_recovery_lines()
            production._sync_reverse_finished_moves()
        res = super().button_mark_done()
        for production in reverse_orders.filtered(lambda p: p.state == 'done'):
            production._action_create_reverse_scraps()
            production._store_reverse_costs()
        return res

    def _sync_reverse_finished_moves(self):
        """Push actual quantities, allocation shares and lots onto the
        finished moves right before they are posted."""
        self.ensure_one()
        self._create_update_move_finished()
        for move in self.move_finished_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')):
            line = move.reverse_recovery_line_id
            if not line:
                continue
            move.cost_share = line.allocation_percent
            move.move_line_ids.unlink()
            move.move_line_ids = [Command.create({
                'product_id': line.product_id.id,
                'product_uom_id': line.product_uom_id.id,
                'quantity': line.actual_qty,
                'lot_id': line.lot_id.id or False,
                'location_id': move.location_id.id,
                'location_dest_id': line.destination_location_id.id,
            })]
            move.picked = True

    def _cal_price(self, consumed_moves):
        """Distribute the total recoverable cost across the recovered
        component moves.

        total = |input valuation| + work order cost + extra cost
        move.price_unit = total x cost_share / 100 / qty

        Core mrp_account is a no-op for reverse orders (it is gated on the
        existence of a finished move for ``product_id``), so this override
        owns the whole distribution.
        """
        res = super()._cal_price(consumed_moves)
        if not self.is_reverse:
            return res
        work_center_cost = sum(
            work_order._cal_cost() for work_order in self.workorder_ids)
        input_qty = self.product_uom_id._compute_quantity(
            self.qty_producing or self.product_qty, self.product_id.uom_id)
        extra_cost = self.extra_cost * input_qty
        raw_moves = self.move_raw_ids.filtered(lambda m: m.state != 'cancel')
        input_cost = -sum(
            raw_moves.sudo().stock_valuation_layer_ids.mapped('value'))
        total_cost = input_cost + work_center_cost + extra_cost
        for move in self.move_finished_ids.filtered(
                lambda m: m.state not in ('done', 'cancel') and m.quantity > 0):
            if float_is_zero(move.cost_share, precision_digits=2):
                continue
            if move.product_id.cost_method in ('fifo', 'average'):
                qty = move.product_uom._compute_quantity(
                    move.quantity, move.product_id.uom_id)
                move.price_unit = total_cost * move.cost_share / 100.0 / qty
                # Extra safety net: biz_receipt_transfer_cost now excludes
                # manufacturing moves (production_id set) from its custom
                # cost override at the source, but keep this belt-and-
                # suspenders guard in case use_custom_cost is set another
                # way (e.g. data import) on an installed DB.
                if 'use_custom_cost' in move._fields:
                    move.use_custom_cost = False
                    move.custom_cost_price = 0.0
        return res

    def _store_reverse_costs(self):
        """Persist the calculated cost per line for reporting/audit."""
        self.ensure_one()
        total = (self._get_reverse_input_cost()
                 + sum(wo._cal_cost() for wo in self.workorder_ids)
                 + self.extra_cost * self.product_uom_id._compute_quantity(
                     self.qty_produced or self.product_qty,
                     self.product_id.uom_id))
        for line in self.recovery_line_ids:
            line.calculated_cost = total * line.allocation_percent / 100.0

    def _action_create_reverse_scraps(self):
        """Create + validate a scrap for each shortfall (expected − actual)
        on lines whose policy is 'auto'.

        The scrap consumes from the virtual production location, so it
        documents the loss without touching on-hand quantities or
        valuation: the whole recoverable cost stays on the actually
        recovered components.
        """
        self.ensure_one()
        production_location = self.product_id.with_company(
            self.company_id).property_stock_production
        for line in self.recovery_line_ids:
            if line.scrap_policy != 'auto' or line.scrap_id:
                continue
            if float_is_zero(line.scrap_qty,
                             precision_rounding=line.product_uom_id.rounding):
                continue
            scrap = self.env['stock.scrap'].create({
                'origin': self.name,
                'production_id': self.id,
                'reverse_recovery_line_id': line.id,
                'product_id': line.product_id.id,
                'product_uom_id': line.product_uom_id.id,
                'scrap_qty': line.scrap_qty,
                'location_id': production_location.id,
                'lot_id': line.lot_id.id if line.tracking == 'lot' else False,
                'company_id': self.company_id.id,
            })
            scrap.do_scrap()
            line.scrap_id = scrap
            self.message_post(
                body=_('Scrapped %(qty)s %(uom)s of %(product)s '
                       '(recovery shortfall).',
                       qty=line.scrap_qty,
                       uom=line.product_uom_id.name,
                       product=line.product_id.display_name),
                subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------

    def action_view_reverse_recovered_moves(self):
        self.ensure_one()
        return {
            'name': _('Recovered Moves'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.move_finished_ids.ids)],
        }

    def action_view_reverse_lots(self):
        self.ensure_one()
        lots = (self.recovery_line_ids.lot_id
                | self.move_finished_ids.move_line_ids.lot_id
                | self.move_raw_ids.move_line_ids.lot_id)
        return {
            'name': _('Lots/Serials'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', lots.ids)],
        }
