from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

from ..models.show_loan import operation_marker


class ShowLoanReturnWizard(models.TransientModel):
    _name = 'buz.show.loan.return.wizard'
    _description = 'Create Show Return'

    loan_id = fields.Many2one('buz.show.loan', required=True, readonly=True)
    picking_type_id = fields.Many2one('stock.picking.type', required=True,
                                      domain="[('code', '=', 'internal')]")
    line_ids = fields.One2many('buz.show.loan.return.wizard.line', 'wizard_id')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        loan = self.env['buz.show.loan'].browse(
            values.get('loan_id') or self.env.context.get('default_loan_id')
        ).exists()
        if not loan:
            return values
        picking_types = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'), ('active', '=', True),
            ('company_id', '=', loan.company_id.id),
        ]).filtered(lambda p: 'RBG' in operation_marker(p))
        if len(picking_types) == 1:
            values['picking_type_id'] = picking_types.id
        values['line_ids'] = [Command.create({
            'loan_line_id': line.id,
            'qty_return': line.qty_available,
        }) for line in loan.line_ids if float_compare(
            line.qty_available, 0, precision_rounding=line.uom_id.rounding,
        ) > 0]
        return values

    def action_confirm(self):
        self.ensure_one()
        loan = self.loan_id
        # ล็อกใบยืมก่อนตรวจยอด เพื่อไม่ให้สองหน้าต่างสร้างใบคืนเกินพร้อมกัน
        self.env.cr.execute('SELECT id FROM buz_show_loan WHERE id = %s FOR UPDATE', [loan.id])
        self.env.invalidate_all()
        if loan.state != 'confirmed' or not loan.picking_id:
            raise UserError(_('The loan is not confirmed.'))
        picking_type = self.picking_type_id
        if (not picking_type.active or picking_type.code != 'internal'
                or picking_type.company_id != loan.company_id
                or 'RBG' not in operation_marker(picking_type)):
            raise ValidationError(_('Select an active RBG Internal Transfer type for this company.'))
        dest = picking_type.default_location_dest_id
        if dest.complete_name != 'FG40/Stock' or dest.company_id not in (loan.company_id, False):
            raise ValidationError(_('The RBG Operation Type must end at FG40/Stock.'))
        source = loan.location_dest_id
        if source == dest:
            raise ValidationError(_('The return source and destination must differ.'))

        seen = set()
        move_commands = []
        for row in self.line_ids:
            line = row.loan_line_id
            if line.loan_id != loan or line.id in seen:
                raise ValidationError(_('Return lines must belong to this loan and be unique.'))
            seen.add(line.id)
            if float_compare(row.qty_return, 0, precision_rounding=line.uom_id.rounding) < 0:
                raise ValidationError(_('Return quantity cannot be negative.'))
            if float_compare(row.qty_return, line.qty_available,
                             precision_rounding=line.uom_id.rounding) > 0:
                raise ValidationError(_('Return quantity exceeds the available loan balance.'))
            if float_compare(row.qty_return, 0, precision_rounding=line.uom_id.rounding) == 0:
                continue
            move_commands.append(Command.create({
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom': line.uom_id.id,
                'product_uom_qty': row.qty_return,
                'location_id': source.id,
                'location_dest_id': dest.id,
                'company_id': loan.company_id.id,
                'show_loan_line_id': line.id,
            }))
        if not move_commands:
            raise ValidationError(_('Enter at least one return quantity.'))

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'company_id': loan.company_id.id,
            'partner_id': loan.partner_id.id,
            'location_id': source.id,
            'location_dest_id': dest.id,
            'origin': loan.picking_id.name,
            'show_loan_id': loan.id,
            'show_loan_role': 'return',
            'move_ids_without_package': move_commands,
        })
        picking.action_confirm()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Show Return'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': picking.id,
        }


class ShowLoanReturnWizardLine(models.TransientModel):
    _name = 'buz.show.loan.return.wizard.line'
    _description = 'Show Return Line'

    wizard_id = fields.Many2one('buz.show.loan.return.wizard', required=True, ondelete='cascade')
    loan_line_id = fields.Many2one('buz.show.loan.line', required=True, readonly=True)
    product_id = fields.Many2one(related='loan_line_id.product_id')
    qty_available = fields.Float(related='loan_line_id.qty_available')
    uom_id = fields.Many2one(related='loan_line_id.uom_id')
    qty_return = fields.Float(string='Return Quantity', digits='Product Unit of Measure')
