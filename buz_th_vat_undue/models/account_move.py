from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    tax_invoice_number = fields.Char(string="Tax Invoice Number", copy=False)
    tax_invoice_date = fields.Date(string="Tax Invoice Date", copy=False)
    has_vat_undue = fields.Boolean(compute='_compute_has_vat_undue', store=True)

    @api.depends('invoice_line_ids.tax_ids')
    def _compute_has_vat_undue(self):
        for move in self:
            move.has_vat_undue = any(t.is_vat_undue for t in move.invoice_line_ids.tax_ids)

    def _post(self, soft=True):
        # Validate before posting
        for move in self:
            if move.has_vat_undue and move.move_type in ('in_invoice', 'in_refund'):
                if not move.tax_invoice_number:
                    raise UserError(_("Tax Invoice Number is required for bills with VAT Undue."))
                if not move.tax_invoice_date:
                    raise UserError(_("Tax Invoice Date is required for bills with VAT Undue."))
        
        posted = super()._post(soft)
        
        # Create Tax Undue Lines
        for move in self:
            if move.has_vat_undue and move.move_type == 'in_invoice':
                move._create_vat_undue_lines()
            elif move.move_type == 'in_refund':
                move._handle_vat_undue_refund()
                
        return posted

    def _create_vat_undue_lines(self):
        TaxUndueLine = self.env['tax.undue.line']
        created = self.env['tax.undue.line']
        for line in self.line_ids:
            if line.tax_line_id and line.tax_line_id.is_vat_undue:
                # Determine sign
                amount = line.balance
                # In Odoo, Debit is positive, Credit is negative.
                # Purchase Tax is Debit (positive).
                # Refund Tax is Credit (negative).
                # We want the signed amount roughly, but usually displayed as absolute in forms with 'Refund' type.
                # However, the requirement says "Tax Undue line (negative amount)".
                # So we keep the sign of 'balance' (assuming Dr is +).
                # But wait, tax_amount in schema is Monetary.
                
                limit_amount = line.balance
                
                undue = TaxUndueLine.create({
                    'name': self.tax_invoice_number,
                    'move_id': self.id,
                    'partner_id': self.partner_id.id,
                    'tax_invoice_date': self.tax_invoice_date,
                    'tax_id': line.tax_line_id.id,
                    'account_id': line.account_id.id,
                    'tax_rate': line.tax_line_id.amount,
                    'tax_base': line.tax_base_amount,
                    'tax_amount': limit_amount,
                    'used_tax_amount': 0.0,
                    'company_id': self.company_id.id,
                })
                created += undue
        return created

    def _create_refund_vat_reclassification(self, original_undue_lines):
        """
        สร้าง Journal Entry เพื่อ reclassify จาก Undue Account ไปเป็น Input VAT Account
        และ Reverse journal entry จาก Use VAT
        """
        journal = self.env['account.journal'].search([('type', '=', 'general'), ('company_id', '=', self.company_id.id)], limit=1)
        if not journal:
            raise UserError(_("Please define a General Journal for this company."))
        
        # กลับรายการ (Reverse) Journal Entries จาก Use VAT
        for undue_line in original_undue_lines:
            if undue_line.state == 'used' and undue_line.used_move_id:
                # ตรวจสอบว่า journal entry ยังไม่ถูก reverse
                if undue_line.used_move_id.state == 'posted' and not undue_line.used_move_id.reversal_move_id:
                    _logger.info(f"Reversing Use VAT journal entry: {undue_line.used_move_id.name}")
                    
                    # สร้าง reversal entry ด้วยวันที่เดียวกับ entry ต้นฉบับ
                    reversal_vals = {
                        'move_ids': [(4, undue_line.used_move_id.id)],
                        'date': undue_line.used_move_id.date,  # ใช้วันที่เดียวกับ Use VAT entry
                        'reason': _("Reverse VAT Usage due to Credit Note: %s") % self.name,
                        'journal_id': undue_line.used_move_id.journal_id.id,
                    }
                    
                    reversal_wizard = self.env['account.move.reversal'].create(reversal_vals)
                    reversal_action = reversal_wizard.reverse_moves()
                    
                    # หา reversal move ที่สร้าง
                    if reversal_action and 'res_id' in reversal_action:
                        reversal_move = self.env['account.move'].browse(reversal_action['res_id'])
                        _logger.info(f"Created reversal entry: {reversal_move.name}")
                    
                    # ลบ Tax Invoice Records ที่สร้างจาก Use VAT
                    tax_invoices_to_remove = self.env['account.move.tax.invoice'].search([
                        ('move_id', '=', undue_line.used_move_id.id)
                    ])
                    if tax_invoices_to_remove:
                        _logger.info(f"Removing {len(tax_invoices_to_remove)} tax invoice records from Use VAT entry")
                        # ใช้ context force_remove_tax_invoice เพื่อบังคับลบ
                        tax_invoices_to_remove.with_context(force_remove_tax_invoice=True).sudo().unlink()
                    
                    # บันทึกจำนวน tax ที่ถูก refund
                    refund_amount = undue_line.used_tax_amount
                    
                    # Update Tax Undue Line: ย้ายจาก used → refunded
                    # เพื่อให้ state เป็น "refund" แทน "undue"
                    undue_line.write({
                        'used_tax_amount': 0.0,
                        'refunded_tax_amount': undue_line.refunded_tax_amount + refund_amount,
                        'used_move_id': False,
                    })
                    
                    _logger.info(f"Updated Tax Undue Line: {undue_line.name}, refunded={refund_amount}, state will recompute to 'refund'")
        
        # ไม่ต้องสร้าง Reclassification Entry แล้ว เพราะเราทำ Reversal แทน
        # Journal Entry จะกลับไปสถานะก่อน Use VAT
        _logger.info("VAT Undue refund processing complete - journal entries reversed")

    def _handle_vat_undue_refund(self):
        # Credit Note logic
        # If we are reversing a bill, check if the original bill had undue tax
        reversed_move = self.reversed_entry_id
        if reversed_move:
             # Logic 11.1 & 11.2 check
             # Check if original undue lines are used
             undue_lines = self.env['tax.undue.line'].search([('move_id', '=', reversed_move.id)])
             if undue_lines:
                 # If any are used?
                 # Requirement 11.1: If BEFORE used (state=undue), create negative undue line.
                 # Requirement 11.2: If AFTER used, Reverse Input VAT.
                 
                 # Logic: Check if all undue lines are used? Or line by line?
                 # Simplification: If the related bill has ANY used lines, we treat it as used?
                 # Better: Check the state.
                 
                 # But a credit note might be partial.
                 # If we have mixed state (some used, some not), it complicates things.
                 # Assuming "Use VAT" is per bill usually.
                 
                 all_unused = all(l.state == 'undue' for l in undue_lines)
                 
                 if all_unused:
                     # 11.1 Create Tax Undue line (negative)
                     created_cn_lines = self._create_vat_undue_lines()
                     
                     # Update Original Undue Lines to mark as Refunded
                     cn_tax_map = {}
                     cn_tax_lines = {} # Map tax -> [cn_lines]
                     
                     # Group CN lines by Tax
                     for cn_line in created_cn_lines:
                         if cn_line.tax_id not in cn_tax_lines:
                             cn_tax_lines[cn_line.tax_id] = []
                         cn_tax_lines[cn_line.tax_id].append(cn_line)
                         
                         cn_tax_map[cn_line.tax_id] = cn_tax_map.get(cn_line.tax_id, 0.0) + abs(cn_line.tax_amount)
                    
                     for undue in undue_lines:
                         if undue.tax_id in cn_tax_map:
                             amount_to_refund = cn_tax_map[undue.tax_id]
                             if amount_to_refund > 0:
                                 # We can only refund up to what's remaining
                                 assign = min(amount_to_refund, undue.remaining_tax_amount)
                                 if assign > 0:
                                     # Refund the Original Bill line
                                     undue.refunded_tax_amount += assign
                                     
                                     # Also Refund (offset) the CN line itself
                                     # We need to distribute 'assign' (negative equivalent) to cn_lines
                                     remaining_assign = assign
                                     if undue.tax_id in cn_tax_lines:
                                         for cn_l in cn_tax_lines[undue.tax_id]:
                                             if remaining_assign <= 0:
                                                 break
                                             # CN line tax_amount is negative. remaining_tax_amount is negative.
                                             # We want to bring remaining close to 0.
                                             # So we add negative amount to refunded_tax_amount?
                                             # Formula: remaining = amount - used - refunded
                                             # 0 = -X - 0 - (-X)
                                             # So refunded should be -X.
                                             
                                             # Check how much "room" this CN line has to offset.
                                             # Its absolute amount is abs(cn_l.tax_amount).
                                             # Its current refunded amount is cn_l.refunded_tax_amount (should be 0 or negative).
                                             # We want to decrease remaining (make it less negative, i.e. add positive).
                                             # Wait, remaining is negative. To make it 0, we must ADD to it.
                                             # amount (-10) - used (0) - refunded (-10) = 0.
                                             
                                             # How much of 'assign' covers this line?
                                             # 'assign' is positive amount being offset.
                                             
                                             current_cn_abs_remaining = abs(cn_l.remaining_tax_amount)
                                             cn_offset = min(remaining_assign, current_cn_abs_remaining)
                                             
                                             cn_l.refunded_tax_amount -= cn_offset
                                             remaining_assign -= cn_offset

                                     cn_tax_map[undue.tax_id] -= assign
                 else:
                     # 11.2 Reverse Input VAT - สร้าง reclassification entry
                     # CN ปกติจะ Cr Undue Account (ลด Undue)
                     # แต่ถ้า VAT ถูกใช้ไปแล้ว ต้องกลับรายการ Input VAT แทน
                     self._create_refund_vat_reclassification(undue_lines)
        else:
            # Standalone Credit Note with Undue Tax?
            # Treat as reduction of Undue?
            if self.has_vat_undue:
                self._create_vat_undue_lines()

