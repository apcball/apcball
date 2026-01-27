# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class VatUndeDiagnosticWizard(models.TransientModel):
    _name = 'vat.undue.diagnostic.wizard'
    _description = 'VAT Undue Diagnostic & Fix Wizard'

    diagnostic_result = fields.Text(string="Diagnostic Result", readonly=True)
    move_ids = fields.Many2many('account.move', string="Problematic Journal Entries", readonly=True)
    has_issues = fields.Boolean(string="Has Issues", default=False)

    def action_diagnose(self):
        """ตรวจสอบ Journal Entries ที่เกี่ยวข้องกับ VAT Undue"""
        issues = []
        problematic_moves = self.env['account.move']
        
        # ค้นหา Journal Entries ที่เกี่ยวข้องกับ VAT Undue
        undue_lines = self.env['tax.undue.line'].search([('state', '=', 'used')])
        
        for undue_line in undue_lines:
            if not undue_line.used_move_id:
                continue
                
            move = undue_line.used_move_id
            
            # ตรวจสอบ 1: ต้องมี 2 lines (Debit Input VAT, Credit Undue)
            if len(move.line_ids) != 2:
                issues.append(f"❌ Move {move.name}: มี {len(move.line_ids)} lines แทนที่จะมี 2 lines")
                problematic_moves |= move
                continue
            
            # ตรวจสอบ 2: ต้องมีบัญชี Input VAT (116400)
            input_vat_account = undue_line.tax_id.undue_input_vat_account_id
            if not input_vat_account:
                issues.append(f"❌ Tax {undue_line.tax_id.name}: ไม่ได้ตั้งค่า Input VAT Account")
                continue
            
            has_input_vat_line = any(
                line.account_id.id == input_vat_account.id 
                for line in move.line_ids
            )
            
            if not has_input_vat_line:
                issues.append(f"❌ Move {move.name}: ไม่มีบัญชี Input VAT {input_vat_account.code} - {input_vat_account.name}")
                problematic_moves |= move
                
                # แสดงบัญชีที่ใช้จริง
                accounts_used = ", ".join([f"{l.account_id.code} ({l.debit or -l.credit:.2f})" for l in move.line_ids])
                issues.append(f"  → ใช้บัญชี: {accounts_used}")
            
            # ตรวจสอบ 3: Debit/Credit ต้องถูกต้อง
            for line in move.line_ids:
                if line.account_id.id == input_vat_account.id:
                    # Input VAT ต้อง Debit
                    if line.debit <= 0:
                        issues.append(f"❌ Move {move.name}: Input VAT Account ต้อง Debit แต่มี Debit={line.debit}, Credit={line.credit}")
                        problematic_moves |= move
                        
                elif line.account_id.id == undue_line.account_id.id:
                    # Undue Account ต้อง Credit
                    if line.credit <= 0:
                        issues.append(f"❌ Move {move.name}: Undue Account ต้อง Credit แต่มี Debit={line.debit}, Credit={line.credit}")
                        problematic_moves |= move
            
            # ตรวจสอบ 4: Balance ต้องเท่ากัน
            total_debit = sum(line.debit for line in move.line_ids)
            total_credit = sum(line.credit for line in move.line_ids)
            
            if abs(total_debit - total_credit) > 0.01:
                issues.append(f"❌ Move {move.name}: ไม่ Balance! Debit={total_debit:.2f}, Credit={total_credit:.2f}")
                problematic_moves |= move
        
        # สรุปผล
        if not issues:
            result = "✅ ไม่พบปัญหา! การลงบัญชี VAT Undue ทั้งหมดถูกต้อง\n\n"
            result += f"ตรวจสอบแล้ว {len(undue_lines)} รายการ"
        else:
            result = f"🔍 พบปัญหา {len(issues)} รายการ:\n\n"
            result += "\n".join(issues)
            result += f"\n\n📊 รายการที่มีปัญหา: {len(problematic_moves)} entries"
        
        self.write({
            'diagnostic_result': result,
            'move_ids': [(6, 0, problematic_moves.ids)],
            'has_issues': bool(issues)
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Diagnostic Result',
            'res_model': 'vat.undue.diagnostic.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def action_view_problematic_moves(self):
        """เปิดดู Journal Entries ที่มีปัญหา"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Problematic Journal Entries',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.move_ids.ids)],
        }
    
    def action_fix_issues(self):
        """แก้ไขปัญหาที่พบ (ยกเลิกและสร้างใหม่)"""
        if not self.move_ids:
            raise UserError(_("No problematic entries to fix."))
        
        fixed_count = 0
        errors = []
        
        for move in self.move_ids:
            try:
                # หา Tax Undue Line ที่เกี่ยวข้อง
                undue_line = self.env['tax.undue.line'].search([('used_move_id', '=', move.id)], limit=1)
                
                if not undue_line:
                    errors.append(f"Cannot find Tax Undue Line for move {move.name}")
                    continue
                
                # ยกเลิก Journal Entry เดิม
                if move.state == 'posted':
                    move.button_draft()
                move.button_cancel()
                
                # Reset Tax Undue Line status
                undue_line.write({
                    'used_tax_amount': 0.0,
                    'used_move_id': False,
                })
                
                # สร้าง Journal Entry ใหม่
                undue_line.action_use_vat()
                fixed_count += 1
                
            except Exception as e:
                errors.append(f"Error fixing move {move.name}: {str(e)}")
        
        result_msg = f"✅ แก้ไขสำเร็จ {fixed_count} รายการ"
        if errors:
            result_msg += f"\n\n❌ พบข้อผิดพลาด {len(errors)} รายการ:\n" + "\n".join(errors)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Fix Complete',
                'message': result_msg,
                'type': 'success' if fixed_count > 0 else 'warning',
                'sticky': True,
            }
        }
