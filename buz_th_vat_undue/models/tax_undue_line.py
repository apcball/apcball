from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class TaxUndueLine(models.Model):
    _name = 'tax.undue.line'
    _description = 'Tax Undue Line'
    _rec_name = 'name'

    name = fields.Char(string="Tax Invoice No")
    move_id = fields.Many2one('account.move', string="Journal Entry", required=True)
    partner_id = fields.Many2one('res.partner', string="Partner", required=True)
    tax_invoice_date = fields.Date(string="Tax Invoice Date")
    tax_id = fields.Many2one('account.tax', string="Tax", required=True)
    account_id = fields.Many2one('account.account', string="VAT Undue Account", required=True)
    
    tax_rate = fields.Float(string="Tax Rate")
    tax_base = fields.Monetary(string="Tax Base", currency_field='currency_id')
    tax_amount = fields.Monetary(string="Tax Amount", currency_field='currency_id')
    
    state = fields.Selection([
        ('undue', 'Undue'),
        ('refund', 'Refund'),
        ('used', 'Used')
    ], string="State", default='undue', compute='_compute_state', store=True)
    
    used_move_id = fields.Many2one('account.move', string="Usage Journal Entry")
    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', string="Currency", related='company_id.currency_id', store=True)

    # Partial usage handling
    used_tax_amount = fields.Monetary(string="Used Tax Amount", currency_field='currency_id', default=0.0)
    refunded_tax_amount = fields.Monetary(string="Refunded Tax Amount", currency_field='currency_id', default=0.0)
    remaining_tax_amount = fields.Monetary(string="Remaining Tax Amount", currency_field='currency_id', compute='_compute_remaining_tax_amount', store=True)

    origin_move_type = fields.Selection(related='move_id.move_type', store=True, string="Origin Move Type")
    original_undue_line_id = fields.Many2one('tax.undue.line', string="Original Undue Line")

    @api.depends('tax_amount', 'used_tax_amount', 'refunded_tax_amount')
    def _compute_remaining_tax_amount(self):
        for record in self:
            record.remaining_tax_amount = record.tax_amount - record.used_tax_amount - record.refunded_tax_amount

    @api.depends('remaining_tax_amount')
    def _compute_state(self):
        for record in self:
            # Floating point comparison
            if abs(record.remaining_tax_amount) < 0.001:
                # If it was fully refunded, mark as refund. Otherwise used.
                if record.refunded_tax_amount > 0 and record.used_tax_amount == 0:
                     record.state = 'refund'
                else:
                     record.state = 'used'
            elif record.remaining_tax_amount < 0:
                record.state = 'refund'
            else:
                record.state = 'undue'

    def action_use_vat(self):
        """เปิด Wizard ให้ User เลือกวันที่ลงบัญชี"""
        # Validation ก่อนเปิด wizard
        for rec in self:
            if rec.state == 'used':
                raise UserError(_("Selected lines contain already used VAT."))
            if rec.state == 'refund':
                raise UserError(_("Cannot use VAT for refunded lines. This line was already used and then reversed by a Credit Note."))
            if rec.tax_amount == 0:
                raise UserError(_("Cannot use VAT for amount 0."))
            if rec.tax_amount < 0:
                raise UserError(_("Cannot use VAT for negative amount (Credit Note lines)."))
            if rec.remaining_tax_amount <= 0:
                raise UserError(_("No remaining VAT amount to use."))
            if not rec.tax_id.undue_conversion_tax_id:
                raise UserError(_("Please configure the Target VAT Tax on tax %s.") % rec.tax_id.name)
            if not rec.tax_id.undue_input_vat_account_id:
                raise UserError(_("Please configure the Input VAT Account on tax %s.") % rec.tax_id.name)
            
            # ตรวจสอบว่า account_id (Undue Account) ต้องไม่เหมือนกับ Input VAT Account
            if rec.account_id.id == rec.tax_id.undue_input_vat_account_id.id:
                raise UserError(_("VAT Undue Account and Input VAT Account cannot be the same! Please check tax configuration for %s.") % rec.tax_id.name)
        
        # เปิด wizard
        return {
            'type': 'ir.actions.act_window',
            'name': _('Use VAT - Select Accounting Date'),
            'res_model': 'vat.undue.use.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_undue_line_ids': [(6, 0, self.ids)],
            },
        }

    def _process_use_vat(self):
        """ประมวลผลการใช้ VAT (เรียกจาก wizard)"""
        if not self:
            return self.env['account.move']

        # รับวันที่ลงบัญชีจาก context
        accounting_date = self.env.context.get('accounting_date', fields.Date.context_today(self))
        
        # 1. Prepare Single Journal Entry Header
        # Use company/journal from the first record (assuming all selected are from same company)
        first_rec = self[0]
        company = first_rec.company_id
        journal = self.env['account.journal'].search([('type', '=', 'general'), ('company_id', '=', company.id)], limit=1)
        if not journal:
             raise UserError(_("Please define a General Journal for this company."))

        move_vals = {
            'journal_id': journal.id,
            'date': accounting_date,
            'ref': _("Clear Undue VAT (Batch Processed)"), # Updated generic ref
            'move_type': 'entry',
            'line_ids': [], # Will populate inside loop
        }

        # Create the move object first (without lines) to have an ID, or create with lines?
        # Creating with lines is better for atomicity, but let's build vals list first.
        
        move_lines_vals = []
        
        # Track checking variables
        total_debit = 0.0
        total_credit = 0.0
        
        processed_records = self.env['tax.undue.line'] # Keep track of what we actually process

        for rec in self:
            amount = rec.remaining_tax_amount
            if amount == 0:
                continue

            # Validation per line
            if not rec.tax_id.undue_input_vat_account_id:
                raise UserError(_("Input VAT Account not configured for tax %s. Please check the tax configuration.") % rec.tax_id.name)
                
            target_account_id = rec.tax_id.undue_input_vat_account_id.id
            
            if rec.account_id.id == target_account_id:
                raise UserError(_("Source and Target accounts cannot be the same for %s!") % rec.name)

            # Determine Tags
            target_tax = rec.tax_id.undue_conversion_tax_id
            repartition_lines = target_tax.invoice_repartition_line_ids if amount > 0 else target_tax.refund_repartition_line_ids
            rep_line = next((l for l in repartition_lines if l.repartition_type == 'tax'), None)
            
            if not rep_line:
                raise UserError(_("Target Tax %s has no tax repartition line.") % target_tax.name)

            tag_ids = rep_line.tag_ids.ids
            
            # Prepare Line Amounts
            amount_abs = abs(amount)
            if amount > 0:
                line_1_debit, line_1_credit = amount_abs, 0.0
                line_2_debit, line_2_credit = 0.0, amount_abs
            else:
                line_1_debit, line_1_credit = 0.0, amount_abs
                line_2_debit, line_2_credit = amount_abs, 0.0

            total_debit += line_1_debit + line_2_debit
            total_credit += line_1_credit + line_2_credit

            # Append Line 1: Input VAT (Debit normally)
            move_lines_vals.append((0, 0, {
                'name': _("Input VAT: %s") % rec.name,
                'account_id': target_account_id,
                'debit': line_1_debit,
                'credit': line_1_credit,
                'partner_id': rec.partner_id.id,
                'tax_tag_ids': [(6, 0, tag_ids)],
                'tax_line_id': target_tax.id,
                'tax_base_amount': rec.tax_base,
            }))

            # Append Line 2: Undue VAT (Credit normally)
            move_lines_vals.append((0, 0, {
                'name': _("Clear Undue: %s") % rec.name,
                'account_id': rec.account_id.id,
                'debit': line_2_debit,
                'credit': line_2_credit,
                'partner_id': rec.partner_id.id,
            }))
            
            processed_records |= rec

        if not move_lines_vals:
            return self.env['account.move']

        # Update move_vals with all lines
        move_vals['line_ids'] = move_lines_vals

        # Create Single Move
        move = self.env['account.move'].with_context(
            check_move_validity=False,
            skip_invoice_sync=True,
            skip_account_move_synchronization=True
        ).create(move_vals)
        
        # Verify Balance (Should be balanced by logic, but good to check)
        if abs(total_debit - total_credit) > 0.01:
             move.unlink()
             raise UserError(_("Journal Entry is not balanced! Please check configuration."))

        move.action_post()
        
        # Post-process: Create Tax Invoice Records & Update Status for EACH processed record
        # We need to find the corresponding lines in the created move.
        # Since we just created them, we can iterate move.line_ids. 
        # But matching them back to 'rec' is easier if we iterate 'processed_records' and filter lines.
        
        for rec in processed_records:
            target_account_id = rec.tax_id.undue_input_vat_account_id.id
            
            # Find the specific Input VAT line for this rec in the move
            # Match by name or some unique identifier. 
            # We set name to "Input VAT: {rec.name}"
            input_vat_line = move.line_ids.filtered(
                lambda l: l.account_id.id == target_account_id and \
                          l.name == (_("Input VAT: %s") % rec.name)
            )
            
            if input_vat_line:
                # 2. Date Logic: Use Undue Tax Date (rec.tax_invoice_date) NOT accounting_date
                tax_date_to_use = rec.tax_invoice_date or accounting_date
                
                tax_invoice_vals = {
                    'move_id': move.id,
                    'move_line_id': input_vat_line[0].id,
                    'partner_id': rec.partner_id.id,
                    'tax_invoice_number': rec.name,
                    'tax_invoice_date': tax_date_to_use, # CORRECTED DATE
                    'tax_base_amount': rec.tax_base,
                    'balance': rec.remaining_tax_amount,
                }
                self.env['account.move.tax.invoice'].create(tax_invoice_vals)

            # Update Record Status
            rec.write({
                'used_tax_amount': rec.used_tax_amount + rec.remaining_tax_amount,
                'used_move_id': move.id,
            })

        return move
