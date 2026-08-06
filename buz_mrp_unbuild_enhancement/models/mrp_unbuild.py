# Part of buz addons for Mogen Co. See LICENSE file.
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class MrpUnbuild(models.Model):
    _inherit = 'mrp.unbuild'

    bom_id = fields.Many2one(
        'mrp.bom', 'Bill of Material',
        domain="""[
        '|',
            ('product_id', '=', product_id),
            '&',
                ('product_tmpl_id.product_variant_ids', '=', product_id),
                ('product_id','=',False),
        ('type', 'in', ('normal', 'unbuild')),
        '|',
            ('company_id', '=', company_id),
            ('company_id', '=', False)
        ]""",
        check_company=True)
    component_line_ids = fields.One2many(
        'mrp.unbuild.component.line',
        'unbuild_id',
        string='Components',
        copy=True,
    )
    component_line_count = fields.Integer(
        compute='_compute_component_line_count')
    scrap_ids = fields.One2many(
        'stock.scrap', 'unbuild_id', string='Scraps', readonly=True)
    scrap_count = fields.Integer(compute='_compute_scrap_count')
    returned_move_count = fields.Integer(
        compute='_compute_returned_move_count')

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('component_line_ids')
    def _compute_component_line_count(self):
        for unbuild in self:
            unbuild.component_line_count = len(unbuild.component_line_ids)

    @api.depends('scrap_ids')
    def _compute_scrap_count(self):
        for unbuild in self:
            unbuild.scrap_count = len(unbuild.scrap_ids)

    @api.depends('produce_line_ids')
    def _compute_returned_move_count(self):
        # produce_line_ids also contains the finished-product consume move
        # (core sets unbuild_id on it); only count real component returns.
        for unbuild in self:
            unbuild.returned_move_count = len(
                unbuild._get_returned_moves())

    def _get_returned_moves(self):
        self.ensure_one()
        return self.produce_line_ids.filtered(
            lambda m: m.location_dest_id.usage == 'internal')

    # ------------------------------------------------------------------
    # Component line generation (BOM explosion preview)
    # ------------------------------------------------------------------

    @api.onchange('product_id', 'bom_id', 'product_qty')
    def _onchange_generate_component_lines(self):
        """Explode the BOM into editable component lines as soon as the
        user selects product + BOM + quantity (no need to confirm first)."""
        for unbuild in self:
            if unbuild.state != 'draft':
                continue
            if unbuild.product_id and unbuild.bom_id and unbuild.product_qty:
                unbuild.component_line_ids = (
                    unbuild._generate_component_lines())
            else:
                unbuild.component_line_ids = [Command.clear()]

    def action_generate_component_lines(self):
        """Manual refresh button: re-explode the BOM, discarding edits."""
        for unbuild in self:
            if unbuild.state != 'draft':
                raise UserError(_(
                    'Components can only be regenerated in draft state.'))
            unbuild.component_line_ids = unbuild._generate_component_lines()
        return True

    def _generate_component_lines(self):
        """Explode the BOM and return One2many commands for component lines.

        Quantity per line = exploded BOM quantity x unbuild quantity.
        Destination is prefilled from the BOM line default return location,
        falling back to the unbuild destination location.
        """
        self.ensure_one()
        commands = [Command.clear()]
        if not (self.product_id and self.bom_id and self.product_qty):
            return commands
        factor = self.product_uom_id._compute_quantity(
            self.product_qty, self.bom_id.product_uom_id,
        ) / self.bom_id.product_qty
        dummy, lines = self.bom_id.explode(
            self.product_id, factor,
            picking_type=self.bom_id.picking_type_id)
        sequence = 10
        for bom_line, line_data in lines:
            destination = (bom_line.default_return_location_id
                           or self.location_dest_id)
            commands.append(Command.create({
                'sequence': sequence,
                'bom_line_id': bom_line.id,
                'product_id': bom_line.product_id.id,
                'product_uom_id': bom_line.product_uom_id.id,
                'expected_qty': line_data['qty'],
                'quantity': line_data['qty'],
                'receive': True,
                'scrap_qty': 0.0,
                'cost_share': bom_line.cost_share or 0.0,
                'destination_location_id': destination.id,
            }))
            sequence += 10
        return commands

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_component_lines(self):
        """Business validation of component lines before unbuilding."""
        for unbuild in self:
            lines = unbuild.component_line_ids
            if not lines:
                continue
            active_lines = lines.filtered(
                lambda l: l.receive and l.quantity > 0)
            if not active_lines:
                raise ValidationError(_(
                    'Unbuild %(name)s: ไม่มีชิ้นส่วนใดถูกรับเลย กรุณาเปิด '
                    '"Receive" อย่างน้อย 1 รายการ หรือลบรายการ Components '
                    'ทั้งหมดเพื่อใช้พฤติกรรมมาตรฐานของ Odoo',
                    name=unbuild.display_name))
            total_cost_share = sum(active_lines.mapped('cost_share'))
            precision = self.env['decimal.precision'].precision_get(
                'Product Price')
            if float_compare(total_cost_share, 100.0,
                              precision_digits=precision) != 0:
                raise ValidationError(_(
                    'Unbuild %(name)s: ต้องระบุ Cost Share (%%) ของ '
                    'ชิ้นส่วนที่รับทั้งหมดให้รวมกันเป็น 100%% ก่อนยืนยัน '
                    'Unbuild นี้ได้ (ตอนนี้รวม %(total)s%%)',
                    name=unbuild.display_name, total=total_cost_share))
            for line in active_lines:
                if not line.destination_location_id:
                    raise ValidationError(_(
                        'ชิ้นส่วน "%(product)s" ยังไม่ได้ระบุ '
                        'Destination Location',
                        product=line.product_id.display_name))
                if line.destination_location_id.usage != 'internal':
                    raise ValidationError(_(
                        'Destination Location "%(location)s" ของชิ้นส่วน '
                        '"%(product)s" ต้องเป็น Internal Location เท่านั้น',
                        location=line.destination_location_id.display_name,
                        product=line.product_id.display_name))
                rounding = line.product_uom_id.rounding or 0.01
                if float_compare(line.scrap_qty, line.quantity,
                                 precision_rounding=rounding) > 0:
                    raise ValidationError(_(
                        'ชิ้นส่วน "%(product)s": จำนวน Scrap มากกว่าจำนวน '
                        'ที่รับคืน',
                        product=line.product_id.display_name))
                if (line.product_id.tracking != 'none'
                        and not unbuild.mo_id):
                    raise ValidationError(_(
                        'ชิ้นส่วน "%(product)s" มีการติดตาม Lot/Serial '
                        'กรุณาเลือก Manufacturing Order ต้นทางใน Unbuild '
                        'เพื่อให้ Odoo ดึง Lot ที่ใช้ไปได้ถูกต้อง',
                        product=line.product_id.display_name))

    # ------------------------------------------------------------------
    # Stock moves (one move per component line, per-line destination)
    # ------------------------------------------------------------------

    def _prepare_component_move_values(self, line):
        """Prepare stock.move values for one component line.

        Mirrors core ``_generate_move_from_bom_line`` (component branch):
        source is the product's production location, destination is the
        per-line destination chosen by the user.
        """
        self.ensure_one()
        production_location = line.product_id.with_company(
            self.company_id).property_stock_production
        values = {
            'name': self.name,
            'date': self.create_date,
            'bom_line_id': line.bom_line_id.id or False,
            'unbuild_component_line_id': line.id,
            'product_id': line.product_id.id,
            'product_uom_qty': line.quantity,
            'product_uom': line.product_uom_id.id,
            'procure_method': 'make_to_stock',
            'location_id': production_location.id,
            'location_dest_id': line.destination_location_id.id,
            'warehouse_id': line.destination_location_id.warehouse_id.id,
            'unbuild_id': self.id,
            'company_id': self.company_id.id,
        }
        if line.owner_id:
            values['restrict_partner_id'] = line.owner_id.id
        return values

    def _action_create_component_moves(self):
        """Create one produce move per received component line."""
        self.ensure_one()
        moves = self.env['stock.move']
        for line in self.component_line_ids:
            if not line.receive:
                _logger.info(
                    'Unbuild %s: component %s skipped (receive unchecked)',
                    self.name, line.product_id.display_name)
                continue
            rounding = line.product_uom_id.rounding or 0.01
            if float_is_zero(line.quantity, precision_rounding=rounding):
                continue
            move = moves.create(self._prepare_component_move_values(line))
            if ('use_custom_cost' in move._fields
                    and not float_is_zero(line.cost_share,
                                           precision_digits=2)):
                # Other modules (e.g. biz_receipt_transfer_cost) may force
                # a custom cost on every new move at create() time, which
                # would silently bypass the Cost Share (%) valuation below.
                # Only clear it when this line actually opts into a share.
                move.use_custom_cost = False
            moves += move
        return moves

    def _generate_produce_moves(self):
        """Use edited component lines instead of the raw BOM explosion.

        Falls back to the standard behavior (super) for unbuild orders
        without component lines, so other modules and standard flows keep
        working unchanged.
        """
        with_lines = self.filtered('component_line_ids')
        moves = super(
            MrpUnbuild, self - with_lines)._generate_produce_moves()
        for unbuild in with_lines:
            moves += unbuild._action_create_component_moves()
        return moves

    # ------------------------------------------------------------------
    # Scrap
    # ------------------------------------------------------------------

    def _prepare_scrap_values(self, line):
        """Prepare stock.scrap values for one component line.

        The scrap consumes from the line destination location: the produce
        move first receives the full quantity there, then the scrap part
        moves out, leaving quantity - scrap_qty on hand.
        """
        self.ensure_one()
        values = {
            'origin': self.name,
            'unbuild_id': self.id,
            'product_id': line.product_id.id,
            'product_uom_id': line.product_uom_id.id,
            'scrap_qty': line.scrap_qty,
            'location_id': line.destination_location_id.id,
            'company_id': self.company_id.id,
        }
        if line.lot_id:
            values['lot_id'] = line.lot_id.id
        if line.owner_id:
            values['owner_id'] = line.owner_id.id
        if line.package_id:
            values['package_id'] = line.package_id.id
        return values

    def _action_create_scrap(self):
        """Create and validate scrap records for lines with scrap qty."""
        self.ensure_one()
        scraps = self.env['stock.scrap']
        for line in self.component_line_ids:
            rounding = line.product_uom_id.rounding or 0.01
            if not line.receive or float_is_zero(
                    line.scrap_qty, precision_rounding=rounding):
                continue
            scrap = scraps.create(self._prepare_scrap_values(line))
            scrap.action_validate()
            scraps += scrap
            _logger.info(
                'Unbuild %s: scrapped %s x %s from %s',
                self.name, line.scrap_qty,
                line.product_id.display_name,
                line.destination_location_id.display_name)
        return scraps

    # ------------------------------------------------------------------
    # Main action
    # ------------------------------------------------------------------

    def action_unbuild(self):
        """Validate component lines, run the standard unbuild (which now
        generates per-line moves through ``_generate_produce_moves``),
        then create scraps and post a summary in the chatter."""
        self.ensure_one()
        has_lines = bool(self.component_line_ids)
        if has_lines:
            self._validate_component_lines()
        res = super().action_unbuild()
        if has_lines and self.state == 'done':
            self._action_create_scrap()
            self._post_unbuild_summary()
        return res

    def _post_unbuild_summary(self):
        """Chatter message summarizing what happened per component."""
        self.ensure_one()
        parts = []
        for line in self.component_line_ids:
            if not line.receive:
                parts.append(_(
                    '%(product)s: skipped',
                    product=line.product_id.display_name))
            elif line.scrap_qty:
                parts.append(_(
                    '%(product)s: %(qty)s to %(location)s '
                    '(%(scrap)s scrapped)',
                    product=line.product_id.display_name,
                    qty=line.quantity - line.scrap_qty,
                    location=line.destination_location_id.display_name,
                    scrap=line.scrap_qty))
            else:
                parts.append(_(
                    '%(product)s: %(qty)s to %(location)s',
                    product=line.product_id.display_name,
                    qty=line.quantity,
                    location=line.destination_location_id.display_name))
        self.message_post(
            body=_('Unbuild completed. Components: %(summary)s',
                   summary='; '.join(parts)),
            subtype_xmlid='mail.mt_note',
        )

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------

    def action_view_returned_moves(self):
        self.ensure_one()
        return {
            'name': _('Returned Moves'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self._get_returned_moves().ids)],
        }

    def action_view_scraps(self):
        self.ensure_one()
        return {
            'name': _('Scraps'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.scrap',
            'view_mode': 'tree,form',
            'domain': [('unbuild_id', '=', self.id)],
        }

    def action_view_component_lines(self):
        self.ensure_one()
        return {
            'name': _('Components'),
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.unbuild.component.line',
            'view_mode': 'tree',
            'views': [(self.env.ref(
                'buz_mrp_unbuild_enhancement'
                '.mrp_unbuild_component_line_tree_view').id, 'tree')],
            'domain': [('unbuild_id', '=', self.id)],
        }
