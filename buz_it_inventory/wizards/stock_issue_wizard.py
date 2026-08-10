from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class BuzItStockIssueWizard(models.TransientModel):
    _name = 'buz.it.stock.issue.wizard'
    _description = 'Issue IT Stock'

    request_id = fields.Many2one(
        'buz.it.issue.request',
        string='Issue Request',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    line_ids = fields.One2many(
        'buz.it.stock.issue.line',
        'wizard_id',
        string='รายการจ่าย',
    )

    def _is_support_agent(self):
        return self.env.user.has_group(
            'buz_it_helpdesk.group_it_support_agent'
        )

    def action_issue(self):
        self.ensure_one()
        request = self.request_id
        if request.state not in ('submitted', 'partially_issued'):
            raise UserError(_(
                'Only a Submitted or Partially Issued request can be issued.'
            ))
        if not self._is_support_agent():
            raise UserError(_('Only an IT agent can issue items.'))
        lines = self.line_ids.filtered(
            lambda line: not float_is_zero(line.qty, precision_digits=0)
        )
        if not lines:
            raise UserError(_(
                'Please specify the quantity to issue for at least one line.'
            ))
        for line in lines:
            if float_compare(line.qty, 0, precision_digits=0) < 0:
                raise UserError(_(
                    'The issued quantity of %s cannot be negative.',
                    line.item_id.display_name,
                ))
            if not line.location_id:
                raise UserError(_(
                    'Please select the Location for %s.',
                    line.item_id.display_name,
                ))
            if line.location_id.company_id != request.company_id:
                raise UserError(_(
                    'The Location and the request must belong to the same '
                    'company.'
                ))
            if line.item_id.company_id != request.company_id:
                raise UserError(_(
                    'The item and the request must belong to the same '
                    'company.'
                ))
        # Lock the involved quants to prevent concurrent issues from
        # driving stock negative.
        self.env.cr.execute(
            'SELECT id FROM buz_it_stock_quant '
            'WHERE inventory_item_id IN %s FOR UPDATE',
            (tuple(lines.mapped('item_id').ids),),
        )
        for line in lines:
            request_line = line.request_line_id
            if float_compare(
                line.qty, request_line.remaining_qty, precision_digits=0,
            ) > 0:
                raise UserError(_(
                    'Cannot issue more than the remaining quantity of %s. '
                    'Remaining: %s %s.',
                    line.item_id.display_name,
                    request_line.remaining_qty,
                    request_line.unit or '',
                ))
            quant = self.env['buz.it.stock.quant'].sudo().search([
                ('inventory_item_id', '=', line.item_id.id),
                ('location_id', '=', line.location_id.id),
            ], limit=1)
            on_hand = quant.qty if quant else 0.0
            if float_compare(line.qty, on_hand, precision_digits=0) > 0:
                raise UserError(_(
                    'Insufficient stock at %(location)s for %(item)s. '
                    'On hand: %(on_hand)s %(unit)s.',
                    location=line.location_id.display_name,
                    item=line.item_id.display_name,
                    on_hand=on_hand,
                    unit=request_line.unit or '',
                ))
            if not quant:
                quant = self.env['buz.it.stock.quant'].with_context(
                    buz_quant_write=True,
                ).sudo().create({
                    'inventory_item_id': line.item_id.id,
                    'location_id': line.location_id.id,
                    'qty': 0.0,
                })
            quant.with_context(buz_quant_write=True).sudo().write({
                'qty': on_hand - line.qty,
            })
            self.env['buz.it.stock.history'].sudo().create({
                'move_type': 'out',
                'inventory_item_id': line.item_id.id,
                'location_id': line.location_id.id,
                'qty': -line.qty,
                'move_date': fields.Date.context_today(self),
                'reference': request.name,
                'note': _('จ่ายของตามคำขอ %s') % request.name,
                'request_id': request.id,
                'request_line_id': request_line.id,
            })
            request_line.with_context(buz_issue_transition=True).write({
                'issued_qty': request_line.issued_qty + line.qty,
            })
        request._recompute_state_after_issue()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('จ่ายของแล้ว'),
                'message': _('จ่ายของตามคำขอ %s') % request.name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class BuzItStockIssueLine(models.TransientModel):
    _name = 'buz.it.stock.issue.line'
    _description = 'IT Stock Issue Line'

    wizard_id = fields.Many2one(
        'buz.it.stock.issue.wizard',
        ondelete='cascade',
    )
    request_line_id = fields.Many2one(
        'buz.it.issue.request.line',
        string='Request Line',
        required=True,
        ondelete='cascade',
    )
    item_id = fields.Many2one(
        'buz.it.inventory.item',
        string='Item',
        related='request_line_id.item_id',
        readonly=True,
    )
    unit = fields.Char(
        string='Unit',
        related='request_line_id.unit',
        readonly=True,
    )
    requested_qty = fields.Float(
        string='Requested',
        related='request_line_id.requested_qty',
        readonly=True,
        digits=(16, 0),
    )
    issued_qty = fields.Float(
        string='Issued',
        related='request_line_id.issued_qty',
        readonly=True,
        digits=(16, 0),
    )
    cancelled_qty = fields.Float(
        string='Cancelled',
        related='request_line_id.cancelled_qty',
        readonly=True,
        digits=(16, 0),
    )
    remaining_qty = fields.Float(
        string='Remaining',
        related='request_line_id.remaining_qty',
        readonly=True,
        digits=(16, 0),
    )
    company_id = fields.Many2one(
        'res.company',
        related='request_line_id.request_id.company_id',
        string='Company',
        readonly=True,
    )
    location_id = fields.Many2one(
        'buz.it.stock.location',
        string='Location',
        domain="[('company_id', '=', company_id)]",
    )
    qty = fields.Float(
        string='To Issue',
        digits=(16, 0),
        default=0.0,
    )
