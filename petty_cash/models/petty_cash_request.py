
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

try:
    from num2words import num2words
except ImportError:
    _logger.warning("The num2words python library is not installed, amount-to-text features won't be fully available.")
    num2words = None


class pettyCashRequest(models.Model):
    _name = "petty.cash.request"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "id desc"
    _description = "Petty Cash Request"

    name = fields.Char('Name', default=_('New'))
    narration = fields.Char('Narration', required=True)
    order_date = fields.Date('Order Date', default=lambda self: fields.Date.today())
    approve_date = fields.Date('Approve Date')

    by_employee = fields.Boolean('By Employee', default=False)
    use_analytic = fields.Boolean('Use Analytic', default=False)

    requester_emp_id = fields.Many2one('hr.employee', 'Employee Requester')
    requester_partner_id = fields.Many2one('res.partner', 'Partner Requester')
    move_id = fields.Many2one('account.move', 'Journal Entry')
    operation_account_id = fields.Many2one('account.account', 'Operation Account', default=lambda self : self.env.company.account_journal_suspense_account_id)
    operation_journal_id = fields.Many2one('account.journal', 'Operation Journal', domain=[('type', 'in', ('bank', 'cash'))])
    petty_cash_journal_id = fields.Many2one('account.journal', 'Petty Cash Journal',
                                            default=lambda self: self.env.ref('petty_cash.petty_cash_journal', raise_if_not_found=False))
    user_id = fields.Many2one('res.users', string='User', required=False, default=lambda self: self.env.user)

    settlement_ids = fields.One2many('petty.cash.settlement', 'petty_request_id', string='Settlements')

    analytic_distribution = fields.Json()
    analytic_precision = fields.Integer(
        store=False,
        default=lambda self: self.env['decimal.precision'].precision_get("Percentage Analytic"),
    )

    amount = fields.Float('Petty Cash Amount', required=True)
    settlement_amount = fields.Float('Settlement Amount', compute='_compute_settlement', store=True)
    different_amount = fields.Float('Different Amount', compute='_compute_different_amount', store=True)
    in_settlement = fields.Boolean('In Settlement', default=False, compute='_compute_settlement')
    has_request_not_reconciled = fields.Boolean('Has Request Not Reconciled',
                                                default=False, compute='_compute_has_request_not_reconciled')
    settlement_state = fields.Selection([
        ('no', 'Not Yet'),
        ('partial', 'Partial Settlement'),
        ('full', 'Full Settlement')], string='Settlement Status', default='no', compute='_set_settlement_status')
    state = fields.Selection([
        ('draft', 'Request'),
        ('approval', 'Approval'),
        ('complete', 'Complete'),
        ('reject', 'Rejected')], string='Status', default='draft')

    note = fields.Text(string='Notes')
    attachment_ids = fields.Many2many('ir.attachment', string='Shared attachments')

    @api.model
    def create(self, vals_list):
        if not vals_list.get('name', False) or vals_list['name'] == _('New'):
            vals_list['name'] = self.env['ir.sequence'].next_by_code('petty.cash.request') or _('New')
        return super().create(vals_list)

    @api.constrains('settlement_ids')
    def _check_settlements_amount(self):
        for rec in self:
            if sum(rec.settlement_ids.mapped('amount')) > rec.amount:
                raise ValidationError(_("You cannot settle a balance higher than the petty cash"))

    @api.depends('settlement_ids')
    def _compute_settlement(self):
        for rec in self:
            rec.settlement_amount = 0.0
            rec.different_amount = 0.0
            rec.in_settlement = False
            if rec.settlement_ids:
                rec.settlement_amount = sum(s.amount for s in rec.settlement_ids)
                if any(not settlement.is_reconciled for settlement in rec.settlement_ids):
                    rec.in_settlement = True
            rec.different_amount = rec.amount - rec.settlement_amount

    @api.depends('amount', 'settlement_amount')
    def _compute_different_amount(self):
        for rec in self:
            rec.different_amount = rec.amount - rec.settlement_amount

    def _set_settlement_status(self):
        for rec in self:
            if 0 < rec.settlement_amount < rec.amount:
                rec.settlement_state = 'partial'
            elif rec.settlement_amount == rec.amount or rec.settlement_amount > rec.amount:
                rec.settlement_state = 'full'
            else:
                rec.settlement_state = 'no'

    def _compute_has_request_not_reconciled(self):
        for rec in self:
            rec.has_request_not_reconciled = False
            all_partner_request = self.search([('id', '!=', rec.id), ('requester_partner_id', '=', rec.requester_partner_id.id)])
            if all_partner_request and all_partner_request.filtered(lambda r: r.settlement_state != 'full') and rec.state == 'draft':
                rec.has_request_not_reconciled = True

    @api.onchange('requester_emp_id')
    def _onchange_requester_emp_id(self):
        if self.requester_emp_id:
            name = self.requester_emp_id.name
            # hr.employee address field name may vary between versions or customizations.
            # Try common attribute names and fallback safely to avoid AttributeError.
            partner = getattr(self.requester_emp_id, 'address_home_id', False) or \
                      getattr(self.requester_emp_id, 'address_id', False) or \
                      getattr(self.requester_emp_id, 'home_address_id', False) or False
            if not partner:
                # reset employee since there's no private contact/partner to use
                self.requester_emp_id = False
                return {
                    'warning': {
                        'title': _("Warning"),
                        'message': _('Please! Add the private contact (Address) of %(name)s from employee profile', name=name)
                    }
                }
            self.requester_partner_id = partner
        else:
            self.requester_partner_id = False

    @api.onchange('operation_journal_id')
    def _onchange_operation_journal_id(self):
        if self.operation_journal_id:
            self.operation_account_id = self.operation_journal_id.default_account_id
        else:
            self.operation_account_id = self.env.company.account_journal_suspense_account_id

    def _prepare_debit_data(self, name, debit_account, debit_amount, partner):
        petty_journal = self.petty_cash_journal_id
        return {
            'name': name,
            'partner_id': partner.id,
            'account_id': debit_account.id,
            'journal_id': petty_journal.id,
            'date': fields.Date.today(),
            'analytic_distribution': self.analytic_distribution and self.analytic_distribution or False,
            'debit': debit_amount,
            'credit': 0.0,
        }

    def _prepare_credit_data(self, name, credit_account, credit_amount, partner):
        petty_journal = self.petty_cash_journal_id
        return {
            'name': name,
            'partner_id': partner.id,
            'account_id': credit_account.id,
            'journal_id': petty_journal.id,
            'date': fields.Date.today(),
            'analytic_distribution': self.analytic_distribution and self.analytic_distribution or False,
            'debit': 0.0,
            'credit': credit_amount,
        }

    def _prepare_move_lines_data(self, operation_account_id, amount):
        petty_journal = self.petty_cash_journal_id
        return [
            (0, 0, self._prepare_debit_data(self.narration, petty_journal.default_account_id, amount, self.requester_partner_id)),
            (0, 0, self._prepare_credit_data(self.narration, operation_account_id, amount, self.requester_partner_id))]

    def _create_account_move(self):
        if self.move_id:
            raise UserError(_("You have already created a journal entry."))
        move_id = self.env['account.move'].create({
            'narration': self.narration,
            'ref': self.name,
            'journal_id': self.petty_cash_journal_id.id,
            'date': fields.Date.today(),
            'move_type': 'entry'
        })
        return move_id

    def action_approve(self):
        for rec in self:
            if rec.has_request_not_reconciled:
                raise ValidationError(_(
                    "%(partner)s has already petty cash isn't full reconciled",
                    partner=rec.requester_partner_id.name,
                ))
            if not rec.petty_cash_journal_id:
                raise UserError(_("Unknown Petty Cash Journal."))
            if not rec.narration:
                raise UserError(_("Add the narration of petty cash."))
            if not rec.amount:
                raise UserError(_("Amount of petty cash must be added."))
            move_id = self._create_account_move()
            if move_id:
                rec.write({'move_id': move_id.id, 'state': 'approval', 'approve_date': fields.Date.today()})
        return True

    def action_reject(self):
        for rec in self:
            if rec.move_id:
                delete_query = "DELETE FROM account_move WHERE id=%s" % rec.move_id
                rec.move_id = False
                self.env.cr.execute(delete_query)
            rec.state = 'reject'
        return True

    def action_draft(self):
        for rec in self:
            rec.state = 'draft'
        return True

    def action_paid(self):
        for rec in self:
            if not rec.move_id:
                raise UserError(_("You should create an journal entry first."))
            if not rec.operation_journal_id:
                raise UserError(_("You should add operation journal."))
            rec.move_id.write({'line_ids': self._prepare_move_lines_data()})
            rec.move_id.action_post()
            rec.state = 'complete'
        return True

    def _reconciliation(self, petty_move_id, reconcile_move_id, petty_account_id):
        (petty_move_id.line_ids.filtered(lambda l: l.account_id == petty_account_id) + reconcile_move_id.line_ids.filtered(
            lambda l: l.account_id == petty_account_id)).reconcile()
        return True

    def confirm_settlement(self):
        for petty in self:

            settlements_with_expenses = petty.settlement_ids.filtered(lambda s: not s.is_reconciled and s.expense_id and s.expense_id.state == 'post')
            settlements_with_bills = petty.settlement_ids.filtered(lambda s: not s.is_reconciled and s.bill_id and s.bill_id.payment_state == 'not_paid')
            settlements_without_bills = petty.settlement_ids.filtered(lambda s: not s.bill_id and not s.expense_id and not s.is_reconciled)

            if settlements_with_expenses:
                settlements_with_expenses._settlement_line_with_expense(petty)

            if settlements_with_bills:
                settlements_with_bills._settlement_line_with_bill(petty)

            if settlements_without_bills:
                if any(not line.expense_account_id for line in settlements_without_bills):
                    raise ValidationError(_("You should add expense account for any settlement line has not bill or expense"))
                settlements_without_bills._settlement_line_without_bill(petty)
        return True

    def _get_context(self):
        context = {'default_petty_request_id': self.id}
        if self.settlement_amount > self.amount:
            context.update({
                'default_amount': self.different_amount,
                'default_is_intemperance': True,
            })
        elif 0 < self.settlement_amount < self.amount:
            context.update({
                'default_amount': self.different_amount,
                'default_is_return': True,
            })
        else:
            context.update({
                'default_amount': self.amount,
            })
        return context

    def open_wizard_operation(self):
        if not self.move_id:
            raise UserError(_("You should create an journal entry first."))
        return {
            'name': _('Operations'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'petty.cash.operations',
            'view_id': self.env.ref("petty_cash.view_petty_cash_operation_form", False).id,
            'target': 'new',
            'context': self._get_context(),
        }

    def petty_cash_settlement(self):
        return {
            'name': _('Confirm'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'petty.cash.request',
            'view_id': self.env.ref("petty_cash.view_petty_confirm_settlement_form", False).id,
            'target': 'new',
            'res_id': self.id,
        }

    def open_reconcile_view(self):
        return {
            'name': _('Journal Entry'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'target': 'current',
        }