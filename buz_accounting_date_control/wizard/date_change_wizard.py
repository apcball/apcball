# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BuzAccountingDateChangeWizard(models.TransientModel):
    """Admin-only wizard to change the accounting date on one or more
    account.moves, bypassing the company policy window (BR-P02, no-approval
    variant). Every change is logged to the immutable audit log as an
    ``override`` event together with the mandatory reason.

    The wizard is bound to ``account.move`` via ``binding_model_id`` so it
    appears in the list-view Action menu. Only ``group_date_admin`` can use
    it (enforced both on the action's ``groups`` attribute and inside
    ``action_apply`` for defense in depth).
    """

    _name = 'buz.accounting.date.change.wizard'
    _description = 'Admin Accounting Date Override'

    move_ids = fields.Many2many(
        comodel_name='account.move',
        string='Journal Entries',
        required=True,
        readonly=True,
    )
    move_count = fields.Integer(
        string='Count', compute='_compute_move_count',
    )
    new_date = fields.Date(
        string='New Accounting Date', required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    new_invoice_date = fields.Date(
        string='New Bill Date',
        help='Optional. Set to also update the vendor/customer bill date '
             '(invoice_date). Leave empty to keep the current value.',
    )
    reason = fields.Text(
        string='Reason', required=True,
    )

    # ------------------------------------------------------------------
    @api.depends('move_ids')
    def _compute_move_count(self):
        for wiz in self:
            wiz.move_count = len(wiz.move_ids)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids') or []
        if active_ids and self.env.context.get('active_model') == 'account.move':
            res['move_ids'] = [(6, 0, active_ids)]
        return res

    # ------------------------------------------------------------------
    def action_apply(self):
        """Apply the new date to every selected move via the override path."""
        self.ensure_one()
        if not self.env.user.has_group(
                'buz_accounting_date_control.group_date_admin'):
            raise UserError(_(
                "Only Accounting Date Administrators may run this action "
                "(BR-P02)."
            ))
        if not self.move_ids:
            raise UserError(_("No journal entries selected."))
        companies = self.move_ids.mapped('company_id')
        if len(companies) > 1:
            raise UserError(_(
                "Selected journal entries belong to different companies. "
                "Process one company at a time."
            ))
        if not self.reason or not self.reason.strip():
            raise UserError(_("A reason is mandatory for an override."))

        self.move_ids.with_context(
            buz_override_date_control=True,
            buz_override_reason=self.reason.strip(),
        ).write(self._buz_build_write_vals())

        msg = _("Accounting date overridden to %(d)s by %(u)s.\nReason: %(r)s")
        for move in self.move_ids:
            move.message_post(body=msg % {
                'd': self.new_date,
                'u': self.env.user.name,
                'r': self.reason.strip(),
            })

        return {'type': 'ir.actions.act_window_close'}

    def _buz_build_write_vals(self):
        """Build the write payload: accounting date always, bill date optional."""
        vals = {'date': self.new_date}
        if self.new_invoice_date:
            vals['invoice_date'] = self.new_invoice_date
        return vals
