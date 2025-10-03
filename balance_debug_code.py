#!/usr/bin/env python3
"""
Simple script to check balance calculation issue
"""
print("=== Balance Calculation Issue ===")

# ให้เพิ่ม debug logging ใน advance_box model เพื่อดูว่าเกิดอะไรขึ้น

balance_debug = '''
# เพิ่ม logging ใน _compute_balance method
import logging
_logger = logging.getLogger(__name__)

def _compute_balance(self):
    for record in self:
        _logger.info("🔍 BALANCE DEBUG: Computing for advance box %s (employee: %s)", 
                   record.id, record.employee_id.name)
        
        if record.account_id and record.employee_id:
            # หา Partner
            partner_id = False
            employee_partner = self.env['res.partner'].search([
                ('name', '=', record.employee_id.name),
                ('is_company', '=', False)
            ], limit=1)
            
            if employee_partner:
                partner_id = employee_partner.id
                _logger.info("🎯 BALANCE DEBUG: Found employee partner %s (ID: %s)", 
                           employee_partner.name, partner_id)
            else:
                # Fallback logic...
                if hasattr(record.employee_id, 'address_home_id') and record.employee_id.sudo().address_home_id:
                    partner_id = record.employee_id.sudo().address_home_id.id
                elif record.employee_id.user_id:
                    partner_id = record.employee_id.user_id.partner_id.id
                elif record.employee_id.address_id:
                    partner_id = record.employee_id.address_id.id
                    
                _logger.info("🔄 BALANCE DEBUG: Using fallback partner ID: %s", partner_id)
            
            if not partner_id:
                _logger.warning("⚠️ BALANCE DEBUG: No partner found, setting balance to 0")
                record.balance = 0.0
                continue
            
            # ค้นหา Account Move Lines
            domain = [
                ('account_id', '=', record.account_id.id),
                ('move_id.state', '=', 'posted'),
                ('partner_id', '=', partner_id),
            ]
            
            _logger.info("📋 BALANCE DEBUG: Searching with domain: %s", domain)
            
            # ใช้ search แทน read_group เพื่อ debug ง่ายขึ้น
            lines = self.env['account.move.line'].search(domain)
            _logger.info("📋 BALANCE DEBUG: Found %d lines", len(lines))
            
            total_debit = sum(lines.mapped('debit'))
            total_credit = sum(lines.mapped('credit'))
            balance = total_debit - total_credit
            
            _logger.info("💰 BALANCE DEBUG: Debit: %s, Credit: %s, Balance: %s", 
                       total_debit, total_credit, balance)
                       
            for line in lines:
                _logger.info("  📝 Line: %s | %s | Dr: %s | Cr: %s | Move: %s", 
                           line.date, line.name, line.debit, line.credit, line.move_id.name)
            
            record.balance = balance
        else:
            _logger.warning("⚠️ BALANCE DEBUG: Missing account or employee")
            record.balance = 0.0
'''

print(balance_debug)
print("\n=== ให้นำ code ข้างบนไปแทนที่ใน advance_box.py ===")
