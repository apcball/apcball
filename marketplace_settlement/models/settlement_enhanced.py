# Enhanced AR/AP Netting functionality for Marketplace Settlement
# This file contains the enhanced netting methods for the new workflow

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero, float_compare


class MarketplaceSettlementEnhanced(models.Model):
    _inherit = 'marketplace.settlement'

    def action_link_vendor_bills(self):
        """Open wizard to link vendor bills to settlement"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Link Vendor Bills'),
            'res_model': 'bill.link.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_settlement_id': self.id,
                'default_partner_id': self.marketplace_partner_id.id,
            },
        }

    def action_preview_netting(self):
        """Preview AR/AP netting before execution"""
        self.ensure_one()
        
        if not self.move_id:
            raise UserError(_('Settlement must be posted before previewing netting.'))
        
        if not self.vendor_bill_ids:
            raise UserError(_('No vendor bills linked to this settlement. Please link vendor bills first.'))
        
        # Calculate netting preview
        preview_data = self._calculate_netting_preview()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('AR/AP Netting Preview'),
            'res_model': 'settlement.preview.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_settlement_id': self.id,
                'default_total_receivables': preview_data['total_receivables'],
                'default_total_payables': preview_data['total_payables'],
                'default_net_amount': preview_data['net_amount'],
                'default_currency_id': self.company_currency_id.id,
                'default_receivable_details': preview_data['receivable_details'],
                'default_payable_details': preview_data['payable_details'],
            },
        }

    def _calculate_netting_preview(self):
        """Calculate preview data for AR/AP netting"""
        self.ensure_one()
        
        # Helper function to check account types
        def _get_account_type(account):
            if hasattr(account, 'account_type'):
                return account.account_type
            elif hasattr(account, 'user_type_id') and hasattr(account.user_type_id, 'type'):
                return account.user_type_id.type
            elif hasattr(account, 'internal_type'):
                return account.internal_type
            return None

        marketplace_partner = self.marketplace_partner_id
        
        # Calculate receivables from settlement
        total_receivables = 0.0
        receivable_details = []
        
        if self.move_id:
            settlement_receivable_lines = self.move_id.line_ids.filtered(
                lambda l: l.partner_id == marketplace_partner and 
                _get_account_type(l.account_id) in ['asset_receivable', 'receivable'] and
                not l.reconciled
            )
            
            for line in settlement_receivable_lines:
                if line.debit > 0:
                    total_receivables += line.debit
                    receivable_details.append(f"• {line.name}: {line.debit:,.2f}")

        # Calculate payables from vendor bills
        total_payables = 0.0
        payable_details = []
        
        for bill in self.vendor_bill_ids:
            bill_payable_lines = bill.line_ids.filtered(
                lambda l: l.partner_id == marketplace_partner and 
                _get_account_type(l.account_id) in ['liability_payable', 'payable'] and
                not l.reconciled
            )
            
            bill_total = 0.0
            for line in bill_payable_lines:
                if line.credit > 0:
                    bill_total += line.credit
                    total_payables += line.credit
            
            if bill_total > 0:
                payable_details.append(f"• {bill.name}: {bill_total:,.2f}")

        net_amount = total_receivables - total_payables
        
        return {
            'total_receivables': total_receivables,
            'total_payables': total_payables,
            'net_amount': net_amount,
            'receivable_details': '\n'.join(receivable_details) if receivable_details else _('No unreconciled receivables found'),
            'payable_details': '\n'.join(payable_details) if payable_details else _('No unreconciled payables found'),
        }

    def action_create_vendor_bill_shopee(self):
        """Quick action to create Shopee vendor bill"""
        self.ensure_one()
        
        # Find Shopee profile for defaults
        shopee_profile = self.env['marketplace.settlement.profile'].search([
            ('trade_channel', '=', 'shopee'),
            ('active', '=', True)
        ], limit=1)
        
        context = {
            'default_document_type': 'shopee_tr',
            'default_trade_channel': 'shopee',
            'default_date': self.date,
        }
        
        if shopee_profile:
            if shopee_profile.vendor_partner_id:
                context['default_partner_id'] = shopee_profile.vendor_partner_id.id
            if shopee_profile.purchase_journal_id:
                context['default_journal_id'] = shopee_profile.purchase_journal_id.id
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Shopee Vendor Bill'),
            'res_model': 'marketplace.vendor.bill',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }

    def action_create_vendor_bill_spx(self):
        """Quick action to create SPX vendor bill"""
        self.ensure_one()
        
        # Find SPX profile for defaults
        spx_profile = self.env['marketplace.settlement.profile'].search([
            ('trade_channel', '=', 'spx'),
            ('active', '=', True)
        ], limit=1)
        
        context = {
            'default_document_type': 'spx_rc',
            'default_trade_channel': 'spx',
            'default_date': self.date,
        }
        
        if spx_profile:
            if spx_profile.vendor_partner_id:
                context['default_partner_id'] = spx_profile.vendor_partner_id.id
            if spx_profile.purchase_journal_id:
                context['default_journal_id'] = spx_profile.purchase_journal_id.id
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create SPX Vendor Bill'),
            'res_model': 'marketplace.vendor.bill',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }

    def action_view_bank_reconciliation(self):
        """Open bank reconciliation for remaining net amount"""
        self.ensure_one()
        
        if not self.netting_move_id:
            raise UserError(_('Please perform AR/AP netting first.'))
        
        # Calculate net amount after netting
        net_amount = self.net_payout_amount
        
        if float_is_zero(net_amount, precision_digits=2):
            raise UserError(_('Net amount is zero. No bank reconciliation needed.'))
        
        # Open bank reconciliation widget or action
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bank Reconciliation'),
            'res_model': 'account.bank.statement',
            'view_mode': 'tree,form',
            'domain': [('journal_id.type', '=', 'bank')],
            'context': {
                'search_default_unreconciled': True,
                'settlement_reference': self.name,
                'expected_amount': net_amount,
            },
        }

    def get_workflow_status(self):
        """Get current workflow status for display"""
        self.ensure_one()
        
        status = {
            'settlement_created': bool(self.move_id),
            'vendor_bills_linked': len(self.vendor_bill_ids) > 0,
            'netting_performed': bool(self.netting_move_id),
            'ready_for_bank_reconciliation': bool(self.netting_move_id) and not float_is_zero(self.net_payout_amount, precision_digits=2),
        }
        
        return status

    def get_workflow_guidance(self):
        """Get workflow guidance text based on current status"""
        self.ensure_one()
        
        status = self.get_workflow_status()
        guidance = []
        
        if not status['settlement_created']:
            guidance.append("✓ Create settlement to group customer invoices → AR-Shopee")
        else:
            guidance.append("✓ Settlement created")
        
        if not status['vendor_bills_linked']:
            guidance.append("• Create and link vendor bills (Shopee/SPX) for fees and taxes")
        else:
            guidance.append("✓ Vendor bills linked")
        
        if not status['netting_performed']:
            guidance.append("• Use 'Net-off AR/AP' to offset receivables against payables")
        else:
            guidance.append("✓ AR/AP netting performed")
        
        if status['ready_for_bank_reconciliation']:
            guidance.append("• Reconcile remaining net amount with bank statement")
        elif status['netting_performed']:
            guidance.append("✓ Complete - Net amount is zero")
        
        return guidance
