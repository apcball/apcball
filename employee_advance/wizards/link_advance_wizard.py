from odoo import api, fields, models, _


class LinkAdvanceWizard(models.TransientModel):
    _name = 'link.advance.wizard'
    _description = 'Link Vendor Bill to Advance Box / Expense Sheet'

    move_id = fields.Many2one('account.move', string='Vendor Bill', required=True)
    advance_box_id = fields.Many2one('employee.advance.box', string='Advance Box', required=True)
    expense_sheet_id = fields.Many2one('hr.expense.sheet', string='Expense Sheet')

    @api.model
    def default_get(self, fields):
        """Set default values for the wizard"""
        res = super().default_get(fields)
        
        # Set the current move_id if passed in context
        if self.env.context.get('active_model') == 'account.move' and self.env.context.get('active_id'):
            res['move_id'] = self.env.context['active_id']
        
        return res

    def action_link(self):
        self.ensure_one()
        move = self.move_id.sudo()
        move.write({
            'advance_box_id': self.advance_box_id.id,
            'expense_sheet_id': self.expense_sheet_id.id if self.expense_sheet_id else False,
            'is_expense_advance_bill': True,
        })
        if self.expense_sheet_id:
            self.expense_sheet_id.sudo().write({'bill_id': move.id})
        move.message_post(body=_('Linked to advance box %s%s') % (
            self.advance_box_id.name,
            (', expense sheet %s' % self.expense_sheet_id.name) if self.expense_sheet_id else ''
        ))
        return {'type': 'ir.actions.act_window_close'}
