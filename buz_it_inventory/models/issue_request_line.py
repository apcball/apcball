from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class BuzItIssueRequestLine(models.Model):
    _name = 'buz.it.issue.request.line'
    _description = 'IT Issue Request Line'

    request_id = fields.Many2one(
        'buz.it.issue.request',
        string='Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    item_id = fields.Many2one(
        'buz.it.inventory.item',
        string='Item',
        required=True,
        ondelete='restrict',
        index=True,
    )
    unit = fields.Char(
        string='Unit',
        related='item_id.unit',
        readonly=True,
    )
    requested_qty = fields.Float(
        string='Requested Qty',
        digits=(16, 0),
        required=True,
        default=0.0,
    )
    approved_qty = fields.Float(
        string='Approved Qty',
        digits=(16, 0),
        default=0.0,
    )
    issued_qty = fields.Float(
        string='Issued Qty',
        digits=(16, 0),
        default=0.0,
    )
    note = fields.Text(string='Note')
    company_id = fields.Many2one(
        'res.company',
        related='request_id.company_id',
        store=True,
        string='Company',
        index=True,
    )
    requester_id = fields.Many2one(
        'res.users',
        related='request_id.requester_id',
        string='Requester',
        store=True,
        index=True,
    )
    state = fields.Selection(
        related='request_id.state',
        string='State',
    )
    available_qty = fields.Float(
        compute='_compute_available_qty',
        string='พร้อมให้เบิก',
        digits=(16, 0),
    )

    @api.depends('item_id.available_qty')
    def _compute_available_qty(self):
        available = self.item_id._get_available_qty()
        for line in self:
            line.available_qty = available.get(line.item_id.id, 0.0)

    @api.constrains('item_id', 'company_id')
    def _check_company_consistency(self):
        for line in self:
            if line.item_id.company_id != line.company_id:
                raise ValidationError(_(
                    'The inventory item and the issue request must belong '
                    'to the same company.'
                ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            request = self.env['buz.it.issue.request'].browse(
                vals.get('request_id')
            )
            if request.state != 'draft':
                raise UserError(_(
                    'Items can only be added while the request is in Draft.'
                ))
        return super().create(vals_list)

    def write(self, vals):
        for line in self:
            state = line.request_id.state
            if state in ('issued', 'rejected', 'cancelled'):
                raise UserError(_(
                    'Request lines cannot be edited after finalization.'
                ))
            if 'requested_qty' in vals and state != 'draft':
                raise UserError(_(
                    'Requested quantity can only be changed in Draft.'
                ))
            if 'approved_qty' in vals and state != 'submitted':
                raise UserError(_(
                    'Approved quantity can only be set in Submitted state.'
                ))
            if 'issued_qty' in vals and state != 'approved':
                raise UserError(_(
                    'Issued quantity can only be set in Approved state.'
                ))
        return super().write(vals)

    def unlink(self):
        for line in self:
            if line.request_id.state != 'draft':
                raise UserError(_(
                    'Items can only be removed while the request is in Draft.'
                ))
        return super().unlink()

    def _issue_stock(self):
        """Deduct the issued quantity from on-hand stock across locations."""
        self.ensure_one()
        remaining = self.issued_qty
        quants = self.env['buz.it.stock.quant'].sudo().search([
            ('inventory_item_id', '=', self.item_id.id),
            ('qty', '>', 0),
        ], order='location_id, id')
        for quant in quants:
            if remaining <= 0:
                break
            take = min(quant.qty, remaining)
            quant.qty -= take
            remaining -= take
            self.env['buz.it.stock.history'].sudo().create({
                'move_type': 'out',
                'inventory_item_id': self.item_id.id,
                'location_id': quant.location_id.id,
                'qty': -take,
                'move_date': fields.Date.context_today(self),
                'reference': self.request_id.name,
                'note': _('จ่ายของตามคำขอ %s') % self.request_id.name,
            })
        if remaining > 0:
            raise UserError(_(
                'Insufficient stock for %s. Missing %s %s.'
            ) % (
                self.item_id.display_name,
                remaining,
                self.unit or '',
            ))
        return True
