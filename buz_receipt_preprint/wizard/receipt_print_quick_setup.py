# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ReceiptPrintQuickSetup(models.TransientModel):
    _name = 'receipt.print.quick.setup'
    _description = 'Quick Setup Wizard for Receipt Print Configuration'
    
    config_id = fields.Many2one('receipt.print.config', string='Configuration')
    config_name = fields.Char(string='Configuration Name', required=True, default='New Receipt Config')
    
    # Quick adjustment fields
    move_all_horizontal = fields.Integer(string='Move All Horizontally (px)', default=0,
                                        help='Positive = right, Negative = left')
    move_all_vertical = fields.Integer(string='Move All Vertically (px)', default=0,
                                      help='Positive = down, Negative = up')
    
    adjust_font_size = fields.Integer(string='Adjust Font Size (px)', default=0,
                                     help='Add or subtract from current font size')
    
    def action_apply_adjustments(self):
        """Apply quick adjustments to configuration"""
        self.ensure_one()
        
        if self.config_id:
            config = self.config_id
        else:
            # Create new config
            config = self.env['receipt.print.config'].create({
                'name': self.config_name,
            })
        
        # Apply horizontal movement
        if self.move_all_horizontal != 0:
            config.write({
                'receipt_number_left': config.receipt_number_left + self.move_all_horizontal,
                'receipt_date_left': config.receipt_date_left + self.move_all_horizontal,
                'payer_name_left': config.payer_name_left + self.move_all_horizontal,
                'payer_address_left': config.payer_address_left + self.move_all_horizontal,
                'payment_description_left': config.payment_description_left + self.move_all_horizontal,
                'amount_numbers_left': config.amount_numbers_left + self.move_all_horizontal,
                'amount_words_left': config.amount_words_left + self.move_all_horizontal,
                'payment_method_left': config.payment_method_left + self.move_all_horizontal,
                'check_number_left': config.check_number_left + self.move_all_horizontal,
                'bank_name_left': config.bank_name_left + self.move_all_horizontal,
                'check_date_left': config.check_date_left + self.move_all_horizontal,
                'signature_payer_left': config.signature_payer_left + self.move_all_horizontal,
                'signature_receiver_left': config.signature_receiver_left + self.move_all_horizontal,
            })
        
        # Apply vertical movement
        if self.move_all_vertical != 0:
            config.write({
                'receipt_number_top': config.receipt_number_top + self.move_all_vertical,
                'receipt_date_top': config.receipt_date_top + self.move_all_vertical,
                'payer_name_top': config.payer_name_top + self.move_all_vertical,
                'payer_address_top': config.payer_address_top + self.move_all_vertical,
                'payment_description_top': config.payment_description_top + self.move_all_vertical,
                'amount_numbers_top': config.amount_numbers_top + self.move_all_vertical,
                'amount_words_top': config.amount_words_top + self.move_all_vertical,
                'payment_method_top': config.payment_method_top + self.move_all_vertical,
                'check_number_top': config.check_number_top + self.move_all_vertical,
                'bank_name_top': config.bank_name_top + self.move_all_vertical,
                'check_date_top': config.check_date_top + self.move_all_vertical,
                'signature_payer_top': config.signature_payer_top + self.move_all_vertical,
                'signature_receiver_top': config.signature_receiver_top + self.move_all_vertical,
            })
        
        # Apply font size adjustment
        if self.adjust_font_size != 0:
            new_font_size = config.font_size + self.adjust_font_size
            new_header_size = config.font_size_header + self.adjust_font_size
            new_small_size = config.font_size_small + self.adjust_font_size
            
            # Ensure within valid range
            if 6 <= new_font_size <= 72:
                config.font_size = new_font_size
            if 6 <= new_header_size <= 72:
                config.font_size_header = new_header_size
            if 6 <= new_small_size <= 72:
                config.font_size_small = new_small_size
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'receipt.print.config',
            'res_id': config.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_reset_to_default(self):
        """Reset configuration to default values"""
        self.ensure_one()
        
        if not self.config_id:
            raise UserError(_('Please select a configuration first'))
        
        self.config_id.action_reset_to_defaults()
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'receipt.print.config',
            'res_id': self.config_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
