from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BuzItIssueRequest(models.Model):
    _name = 'buz.it.issue.request'
    _description = 'IT Issue Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Request Number',
        required=True,
        readonly=True,
        copy=False,
        default='New',
    )
    requester_id = fields.Many2one(
        'res.users',
        string='Requester',
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: self.env.user,
        index=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        readonly=True,
        copy=False,
        index=True,
    )
    request_date = fields.Date(
        string='Request Date',
        required=True,
        readonly=True,
        copy=False,
        default=fields.Date.context_today,
        index=True,
    )
    reason = fields.Text(string='Reason')
    ticket_id = fields.Many2one(
        'buz.helpdesk.ticket',
        string='Helpdesk Ticket',
        ondelete='set null',
        index=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('issued', 'Issued'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='State', required=True, default='draft', tracking=True, copy=False, index=True)
    it_note = fields.Text(string='IT Note')
    rejection_reason = fields.Text(string='Rejection Reason')
    issue_date = fields.Date(
        string='Issue Date',
        readonly=True,
        copy=False,
    )
    issued_by = fields.Many2one(
        'res.users',
        string='Issued By',
        readonly=True,
        copy=False,
    )
    line_ids = fields.One2many(
        'buz.it.issue.request.line',
        'request_id',
        string='Items',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: self.env.company,
        index=True,
    )
    line_count = fields.Integer(
        compute='_compute_line_count',
        store=True,
        string='# Items',
    )
    total_qty = fields.Float(
        compute='_compute_total_qty',
        string='Total Qty',
        digits=(16, 0),
    )

    @api.depends('line_ids', 'line_ids.item_id')
    def _compute_line_count(self):
        for request in self:
            request.line_count = len(request.line_ids)

    @api.depends('line_ids.requested_qty')
    def _compute_total_qty(self):
        for request in self:
            request.total_qty = sum(request.line_ids.mapped('requested_qty'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'buz.it.issue.request'
                ) or 'New'
            requester = self.env['res.users'].browse(
                vals.get('requester_id') or self.env.uid
            )
            if requester.exists() and requester.employee_id:
                vals['department_id'] = (
                    requester.employee_id.department_id.id
                )
            else:
                vals['department_id'] = False
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('buz_issue_transition'):
            for request in self:
                if request.state in ('issued', 'rejected', 'cancelled'):
                    raise UserError(_(
                        'A finalized request cannot be edited.'
                    ))
                if not request._is_support_agent():
                    if request.state != 'draft':
                        raise UserError(_(
                            'Only a Draft request can be edited by the '
                            'requester.'
                        ))
                    if request.requester_id != self.env.user:
                        raise UserError(_(
                            'Only the requester can edit this request.'
                        ))
        return super().write(vals)

    def unlink(self):
        for request in self:
            if request.state != 'draft':
                raise UserError(_('Only Draft requests can be deleted.'))
        return super().unlink()

    def _is_support_agent(self):
        return self.env.user.has_group(
            'buz_it_helpdesk.group_it_support_agent'
        )

    def _is_helpdesk_manager(self):
        return self.env.user.has_group(
            'buz_it_helpdesk.group_it_helpdesk_manager'
        )

    def action_submit(self):
        for request in self:
            if request.state != 'draft':
                raise UserError(_('Only a Draft request can be submitted.'))
            if not request.line_ids:
                raise UserError(_(
                    'Please add at least one item to the request.'
                ))
            items = request.line_ids.item_id
            self.env.cr.execute(
                'SELECT id FROM buz_it_inventory_item '
                'WHERE id IN %s FOR UPDATE',
                (tuple(items.ids),),
            )
            available = items._get_available_qty()
            for line in request.line_ids:
                if line.requested_qty <= 0:
                    raise UserError(_(
                        'Requested quantity for %s must be greater than 0.'
                    ) % line.item_id.display_name)
                if not line.item_id.is_published or not line.item_id.active:
                    raise UserError(_(
                        '%s is not available in the Store.'
                    ) % line.item_id.display_name)
            totals = defaultdict(float)
            for line in request.line_ids:
                totals[line.item_id.id] += line.requested_qty
            for item_id, qty in totals.items():
                available_qty = available.get(item_id, 0.0)
                if qty > available_qty:
                    item = self.env['buz.it.inventory.item'].browse(item_id)
                    raise UserError(_(
                        'Not enough stock for %(item)s. Maximum available '
                        'is %(qty)s %(unit)s.',
                        item=item.display_name,
                        qty=available_qty,
                        unit=item.unit or '',
                    ))
            request.with_context(buz_issue_transition=True).write({
                'state': 'submitted',
            })
        return True

    def action_approve(self):
        for request in self:
            if request.state != 'submitted':
                raise UserError(_(
                    'Only a Submitted request can be approved.'
                ))
            if not request._is_support_agent():
                raise UserError(_('Only an IT agent can approve requests.'))
            for line in request.line_ids:
                if not line.approved_qty or line.approved_qty <= 0:
                    line.approved_qty = line.requested_qty
                if line.approved_qty > line.requested_qty:
                    raise UserError(_(
                        'Approved quantity cannot exceed requested quantity '
                        'for %s.' % line.item_id.display_name
                    ))
            request.with_context(buz_issue_transition=True).write({
                'state': 'approved',
            })
        return True

    def action_reject(self):
        for request in self:
            if request.state != 'submitted':
                raise UserError(_(
                    'Only a Submitted request can be rejected.'
                ))
            if not request._is_support_agent():
                raise UserError(_('Only an IT agent can reject requests.'))
            if not request.rejection_reason:
                raise UserError(_(
                    'Please provide a rejection reason before rejecting.'
                ))
            request.with_context(buz_issue_transition=True).write({
                'state': 'rejected',
            })
        return True

    def action_cancel(self):
        for request in self:
            if request.state not in ('draft', 'submitted'):
                raise UserError(_(
                    'Only a Draft or Submitted request can be cancelled.'
                ))
            if (
                not request._is_support_agent()
                and request.requester_id != self.env.user
            ):
                raise UserError(_(
                    'Only the requester or an IT agent can cancel this '
                    'request.'
                ))
            request.with_context(buz_issue_transition=True).write({
                'state': 'cancelled',
            })
        return True

    def action_issue(self):
        for request in self:
            if request.state != 'approved':
                raise UserError(_(
                    'Only an Approved request can be issued.'
                ))
            if not request._is_support_agent():
                raise UserError(_('Only an IT agent can issue items.'))
            for line in request.line_ids:
                if not line.issued_qty or line.issued_qty <= 0:
                    line.issued_qty = line.approved_qty
                if line.issued_qty > line.approved_qty:
                    raise UserError(_(
                        'Issued quantity cannot exceed approved quantity '
                        'for %s.' % line.item_id.display_name
                    ))
                line._issue_stock()
            request.with_context(buz_issue_transition=True).write({
                'state': 'issued',
                'issue_date': fields.Date.context_today(request),
                'issued_by': self.env.user.id,
            })
        return True
