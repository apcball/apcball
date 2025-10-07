from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BillDisplayWizard(models.TransientModel):
    _name = 'bill.display.wizard'
    _description = 'Bill Display Wizard for Payment Voucher'

    # Fields to display bill information in popup
    partner_id = fields.Many2one('res.partner', string='Vendor', readonly=True)
    voucher_line_id = fields.Many2one('account.payment.voucher.line', string='Voucher Line', readonly=True, ondelete='cascade')
    
    # Related bills for the partner
    bill_ids = fields.One2many('bill.display.wizard.line', 'wizard_id', string='Available Bills')
    
    # Summary fields
    total_bills = fields.Integer(string='Total Bills', compute='_compute_summary', readonly=True)
    total_amount = fields.Monetary(string='Total Amount', compute='_compute_summary', readonly=True)
    total_residual = fields.Monetary(string='Total Outstanding', compute='_compute_summary', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    @api.depends('bill_ids')
    def _compute_summary(self):
        for wizard in self:
            wizard.total_bills = len(wizard.bill_ids)
            wizard.total_amount = sum(line.amount_total for line in wizard.bill_ids)
            wizard.total_residual = sum(line.amount_residual for line in wizard.bill_ids)

    def action_show_bills(self):
        """Load bills for the partner and show them in the popup"""
        self.ensure_one()
        
        if not self.partner_id:
            raise UserError(_("No vendor selected."))
            
        # Search for unpaid and partially paid bills for this partner
        bills = self.env['account.move'].search([
            ('partner_id', '=', self.partner_id.id),
            ('move_type', 'in', ['in_invoice', 'in_refund']),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial'])
        ])
        
        # Clear existing lines and create new ones
        self.bill_ids.unlink()
        bill_lines = []
        
        for bill in bills:
            bill_lines.append((0, 0, {
                'bill_id': bill.id,
                'bill_number': bill.name,
                'bill_date': bill.date,
                'bill_type': bill.move_type,
                'amount_total': bill.amount_total,
                'amount_residual': bill.amount_residual,
                'payment_state': bill.payment_state,
            }))
        
        self.write({'bill_ids': bill_lines})
        
        return {
            'name': _('Bills for %s') % self.partner_id.name,
            'type': 'ir.actions.act_window',
            'res_model': 'bill.display.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_select_bill(self):
        """Action to select a bill for payment registration"""
        self.ensure_one()
        
        # Check if any bill is selected
        selected_bills = self.bill_ids.filtered(lambda l: l.selected)
        
        if not selected_bills:
            raise UserError(_("Please select at least one bill."))
            
        if len(selected_bills) > 1:
            raise UserError(_("Please select only one bill for payment registration."))
            
        selected_bill = selected_bills[0]
        
        # Update the voucher line with the selected bill
        if self.voucher_line_id:
            self.voucher_line_id.write({
                'move_id': selected_bill.bill_id.id,
                'amount_to_pay_gross': abs(selected_bill.bill_id.amount_residual_signed),
                'wht_base_amount': abs(selected_bill.bill_id.amount_residual_signed),
            })
            
        # Close the popup and refresh the parent view
        return {'type': 'ir.actions.act_window_close'}


class BillDisplayWizardLine(models.TransientModel):
    _name = 'bill.display.wizard.line'
    _description = 'Bill Display Wizard Line'

    wizard_id = fields.Many2one('bill.display.wizard', string='Wizard', required=True, ondelete='cascade')
    bill_id = fields.Many2one('account.move', string='Bill', required=True)
    bill_number = fields.Char(string='Bill Number', readonly=True)
    bill_date = fields.Date(string='Bill Date', readonly=True)
    bill_type = fields.Selection([
        ('in_invoice', 'Vendor Bill'),
        ('in_refund', 'Vendor Credit Note')
    ], string='Type', readonly=True)
    amount_total = fields.Monetary(string='Total Amount', readonly=True)
    amount_residual = fields.Monetary(string='Outstanding Amount', readonly=True)
    payment_state = fields.Selection([
        ('not_paid', 'Not Paid'),
        ('in_payment', 'In Payment'),
        ('paid', 'Paid'),
        ('partial', 'Partially Paid'),
        ('reversed', 'Reversed'),
        ('invoicing_legacy', 'Invoicing App Legacy'),
    ], string='Payment Status', readonly=True)
    currency_id = fields.Many2one(related='wizard_id.currency_id', readonly=True)
    selected = fields.Boolean(string='Select', default=False)

    def action_view_bill(self):
        """Action to open the bill in form view"""
        self.ensure_one()
        
        return {
            'name': _('Bill'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.bill_id.id,
            'target': 'current',
        }