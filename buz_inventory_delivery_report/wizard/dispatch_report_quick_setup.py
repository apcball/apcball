# -*- coding: utf-8 -*-
from odoo import models, fields, api

class DispatchReportQuickSetup(models.TransientModel):
    _name = 'dispatch.report.quick.setup'
    _description = 'Quick Setup Wizard for Dispatch Report'
    
    config_id = fields.Many2one('dispatch.report.config', string='Configuration')
    config_name = fields.Char(string='Configuration Name', required=True, default='New Config')
    
    # Quick adjustment fields
    move_all_horizontal = fields.Integer(string='Move All Horizontally (px)', default=0,
                                        help='Positive = right, Negative = left')
    move_all_vertical = fields.Integer(string='Move All Vertically (px)', default=0,
                                      help='Positive = down, Negative = up')
    
    adjust_line_spacing = fields.Integer(string='Adjust Line Spacing (px)', default=0,
                                        help='Add or subtract from current line height')
    
    adjust_font_size = fields.Integer(string='Adjust Font Size (px)', default=0,
                                     help='Add or subtract from current font size')
    
    def action_apply_adjustments(self):
        """Apply quick adjustments to configuration"""
        self.ensure_one()
        
        if self.config_id:
            config = self.config_id
        else:
            # Create new config
            config = self.env['dispatch.report.config'].create({
                'name': self.config_name,
            })
        
        # Apply horizontal movement
        if self.move_all_horizontal != 0:
            config.write({
                'doc_number_left': config.doc_number_left + self.move_all_horizontal,
                'doc_date_left': config.doc_date_left + self.move_all_horizontal,
                'so_number_left': config.so_number_left + self.move_all_horizontal,
                'customer_name_left': config.customer_name_left + self.move_all_horizontal,
                'customer_address_left': config.customer_address_left + self.move_all_horizontal,
                'customer_phone_left': config.customer_phone_left + self.move_all_horizontal,
                'vehicle_type_left': config.vehicle_type_left + self.move_all_horizontal,
                'vehicle_plate_left': config.vehicle_plate_left + self.move_all_horizontal,
                'driver_name_left': config.driver_name_left + self.move_all_horizontal,
                'table_left': config.table_left + self.move_all_horizontal,
                'total_qty_left': config.total_qty_left + self.move_all_horizontal,
                'signature_sender_left': config.signature_sender_left + self.move_all_horizontal,
                'signature_receiver_left': config.signature_receiver_left + self.move_all_horizontal,
            })
        
        # Apply vertical movement
        if self.move_all_vertical != 0:
            config.write({
                'doc_number_top': config.doc_number_top + self.move_all_vertical,
                'doc_date_top': config.doc_date_top + self.move_all_vertical,
                'so_number_top': config.so_number_top + self.move_all_vertical,
                'customer_name_top': config.customer_name_top + self.move_all_vertical,
                'customer_address_top': config.customer_address_top + self.move_all_vertical,
                'customer_phone_top': config.customer_phone_top + self.move_all_vertical,
                'vehicle_type_top': config.vehicle_type_top + self.move_all_vertical,
                'vehicle_plate_top': config.vehicle_plate_top + self.move_all_vertical,
                'driver_name_top': config.driver_name_top + self.move_all_vertical,
                'table_top': config.table_top + self.move_all_vertical,
                'total_qty_top': config.total_qty_top + self.move_all_vertical,
                'signature_sender_top': config.signature_sender_top + self.move_all_vertical,
                'signature_receiver_top': config.signature_receiver_top + self.move_all_vertical,
            })
        
        # Apply line spacing adjustment
        if self.adjust_line_spacing != 0:
            config.write({
                'line_height': config.line_height + self.adjust_line_spacing,
            })
        
        # Apply font size adjustment
        if self.adjust_font_size != 0:
            config.write({
                'font_size': config.font_size + self.adjust_font_size,
            })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dispatch.report.config',
            'res_id': config.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_reset_to_default(self):
        """Reset configuration to default values"""
        self.ensure_one()
        
        if not self.config_id:
            raise UserWarning('Please select a configuration first')
        
        default_config = self.env.ref('buz_inventory_delivery_report.dispatch_report_config_default')
        
        self.config_id.write({
            'doc_number_top': default_config.doc_number_top,
            'doc_number_left': default_config.doc_number_left,
            'doc_date_top': default_config.doc_date_top,
            'doc_date_left': default_config.doc_date_left,
            'so_number_top': default_config.so_number_top,
            'so_number_left': default_config.so_number_left,
            'customer_name_top': default_config.customer_name_top,
            'customer_name_left': default_config.customer_name_left,
            'customer_address_top': default_config.customer_address_top,
            'customer_address_left': default_config.customer_address_left,
            'customer_phone_top': default_config.customer_phone_top,
            'customer_phone_left': default_config.customer_phone_left,
            'vehicle_type_top': default_config.vehicle_type_top,
            'vehicle_type_left': default_config.vehicle_type_left,
            'vehicle_plate_top': default_config.vehicle_plate_top,
            'vehicle_plate_left': default_config.vehicle_plate_left,
            'driver_name_top': default_config.driver_name_top,
            'driver_name_left': default_config.driver_name_left,
            'table_top': default_config.table_top,
            'table_left': default_config.table_left,
            'line_height': default_config.line_height,
            'col_no_left': default_config.col_no_left,
            'col_code_left': default_config.col_code_left,
            'col_name_left': default_config.col_name_left,
            'col_qty_left': default_config.col_qty_left,
            'col_unit_left': default_config.col_unit_left,
            'col_remark_left': default_config.col_remark_left,
            'total_qty_top': default_config.total_qty_top,
            'total_qty_left': default_config.total_qty_left,
            'signature_sender_top': default_config.signature_sender_top,
            'signature_sender_left': default_config.signature_sender_left,
            'signature_receiver_top': default_config.signature_receiver_top,
            'signature_receiver_left': default_config.signature_receiver_left,
            'font_size': default_config.font_size,
            'font_family': default_config.font_family,
            'page_width': default_config.page_width,
            'page_height': default_config.page_height,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Configuration reset to default values',
                'type': 'success',
                'sticky': False,
            }
        }
