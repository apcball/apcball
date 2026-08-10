from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


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
        ('partially_issued', 'Partially Issued'),
        ('done', 'Done'),
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
    remaining_total_qty = fields.Float(
        compute='_compute_remaining_total_qty',
        string='Remaining Total Qty',
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

    @api.depends('line_ids.remaining_qty')
    def _compute_remaining_total_qty(self):
        for request in self:
            request.remaining_total_qty = sum(
                request.line_ids.mapped('remaining_qty')
            )

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
                if request.state in ('done', 'rejected', 'cancelled'):
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
            for line in request.line_ids:
                if line.requested_qty <= 0:
                    raise UserError(_(
                        'Requested quantity for %s must be greater than 0.'
                    ) % line.item_id.display_name)
                if not line.item_id.is_published or not line.item_id.active:
                    raise UserError(_(
                        '%s is not available in the Store.'
                    ) % line.item_id.display_name)
            request.with_context(buz_issue_transition=True).write({
                'state': 'submitted',
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
                    'Only a Draft or Submitted request can be cancelled. '
                    'Outstanding items of an issued request must be ended '
                    'instead.'
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

    def action_issue_stock(self):
        self.ensure_one()
        if self.state not in ('submitted', 'partially_issued'):
            raise UserError(_(
                'Only a Submitted or Partially Issued request can be issued.'
            ))
        if not self._is_support_agent():
            raise UserError(_('Only an IT agent can issue items.'))
        wizard = self.env['buz.it.stock.issue.wizard'].create({
            'request_id': self.id,
            'line_ids': [
                fields.Command.create({'request_line_id': line.id})
                for line in self.line_ids
            ],
        })
        return {
            'name': _('Issue Items'),
            'type': 'ir.actions.act_window',
            'res_model': 'buz.it.stock.issue.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_end_outstanding(self):
        """Close the remaining balance of every line with a cancellation
        reason. Stock is never touched by this action.
        """
        for request in self:
            if request.state not in ('submitted', 'partially_issued'):
                raise UserError(_(
                    'Only a Submitted or Partially Issued request can have '
                    'its outstanding balance ended.'
                ))
            if not request._is_support_agent():
                raise UserError(_(
                    'Only an IT agent can end the outstanding balance.'
                ))
            if not request.line_ids:
                raise UserError(_('This request has no lines.'))
            for line in request.line_ids:
                if (
                    float_compare(line.cancelled_qty, 0, precision_digits=0) > 0
                    and not line.cancel_reason
                ):
                    raise UserError(_(
                        'Please provide the reason for ending the '
                        'outstanding balance of %s.',
                        line.item_id.display_name,
                    ))
                if float_compare(
                    line.remaining_qty, 0, precision_digits=0,
                ) > 0:
                    if not line.cancel_reason:
                        raise UserError(_(
                            'Please provide the reason for ending the '
                            'outstanding balance of %s.',
                            line.item_id.display_name,
                        ))
                    if float_compare(
                        line.cancelled_qty, line.remaining_qty,
                        precision_digits=0,
                    ) < 0:
                        raise UserError(_(
                            'The cancelled quantity of %s must cover its '
                            'remaining quantity (%s %s).',
                            line.item_id.display_name,
                            line.remaining_qty,
                            line.unit or '',
                        ))
            for line in request.line_ids:
                if not float_is_zero(line.remaining_qty, precision_digits=0):
                    line.with_context(buz_issue_transition=True).write({
                        'cancelled_qty': line.remaining_qty,
                    })
            request.with_context(buz_issue_transition=True).write({
                'state': 'done',
            })
        return True

    def _recompute_state_after_issue(self):
        """Recompute the request state after items have been issued."""
        for request in self:
            if request.state not in ('submitted', 'partially_issued'):
                continue
            lines = request.line_ids
            if all(
                float_is_zero(line.remaining_qty, precision_digits=0)
                for line in lines
            ):
                request.with_context(buz_issue_transition=True).write({
                    'state': 'done',
                    'issue_date': fields.Date.context_today(request),
                    'issued_by': self.env.user.id,
                })
            elif any(
                not float_is_zero(line.issued_qty, precision_digits=0)
                for line in lines
            ):
                request.with_context(buz_issue_transition=True).write({
                    'state': 'partially_issued',
                    'issue_date': fields.Date.context_today(request),
                    'issued_by': self.env.user.id,
                })
