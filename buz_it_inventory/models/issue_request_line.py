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
    issued_qty = fields.Float(
        string='Issued Qty',
        digits=(16, 0),
        default=0.0,
        help='ยอดที่จ่ายจริงสะสม',
    )
    cancelled_qty = fields.Float(
        string='Cancelled Qty',
        digits=(16, 0),
        default=0.0,
        help='จำนวนที่ยุติยอดค้างของรายการนี้',
    )
    cancel_reason = fields.Text(
        string='Cancel Reason',
        help='เหตุผลที่ยุติยอดค้าง',
    )
    remaining_qty = fields.Float(
        compute='_compute_remaining_qty',
        store=True,
        string='ยอดคงค้าง',
        digits=(16, 0),
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

    @api.depends('requested_qty', 'issued_qty', 'cancelled_qty')
    def _compute_remaining_qty(self):
        for line in self:
            line.remaining_qty = (
                line.requested_qty - line.issued_qty - line.cancelled_qty
            )

    @api.depends('item_id.available_qty')
    def _compute_available_qty(self):
        for line in self:
            line.available_qty = line.item_id.available_qty

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
            if state in ('done', 'rejected', 'cancelled'):
                raise UserError(_(
                    'Request lines cannot be edited after finalization.'
                ))
            if 'requested_qty' in vals and state != 'draft':
                raise UserError(_(
                    'Requested quantity can only be changed in Draft.'
                ))
            if 'item_id' in vals and state != 'draft':
                raise UserError(_(
                    'The item can only be changed in Draft.'
                ))
            if 'issued_qty' in vals and not self.env.context.get(
                'buz_issue_transition'
            ):
                raise UserError(_(
                    'Issued quantity can only be changed through the '
                    'Issue wizard.'
                ))
            if (
                'cancelled_qty' in vals or 'cancel_reason' in vals
            ) and not self._current_user_is_support_agent():
                raise UserError(_(
                    'Only an IT agent can end the outstanding balance.'
                ))
        return super().write(vals)

    def unlink(self):
        for line in self:
            if line.request_id.state != 'draft':
                raise UserError(_(
                    'Items can only be removed while the request is in Draft.'
                ))
        return super().unlink()

    def _current_user_is_support_agent(self):
        return self.env.user.has_group(
            'buz_it_helpdesk.group_it_support_agent'
        )
