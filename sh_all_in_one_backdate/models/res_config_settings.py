# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    backdate_max_days = fields.Integer(
        string='Maximum Backdate Days',
        default=30,
        config_parameter='sh_all_in_one_backdate.backdate_max_days',
        help='Maximum number of days users can backdate documents (0 = unlimited for managers)'
    )
    
    backdate_require_reason = fields.Boolean(
        string='Require Reason for Backdating',
        default=True,
        config_parameter='sh_all_in_one_backdate.backdate_require_reason',
        help='Require users to provide a reason when backdating documents'
    )
    
    backdate_enable_invoice = fields.Boolean(
        string='Enable Invoice Backdating',
        default=True,
        config_parameter='sh_all_in_one_backdate.backdate_enable_invoice',
        help='Allow backdating of customer invoices and vendor bills'
    )
    
    backdate_enable_payment = fields.Boolean(
        string='Enable Payment Backdating',
        default=True,
        config_parameter='sh_all_in_one_backdate.backdate_enable_payment',
        help='Allow backdating of payments'
    )
    
    backdate_enable_sale = fields.Boolean(
        string='Enable Sale Order Backdating',
        default=True,
        config_parameter='sh_all_in_one_backdate.backdate_enable_sale',
        help='Allow backdating of sale orders'
    )
    
    backdate_enable_purchase = fields.Boolean(
        string='Enable Purchase Order Backdating',
        default=True,
        config_parameter='sh_all_in_one_backdate.backdate_enable_purchase',
        help='Allow backdating of purchase orders'
    )
    
    backdate_enable_picking = fields.Boolean(
        string='Enable Picking Backdating',
        default=True,
        config_parameter='sh_all_in_one_backdate.backdate_enable_picking',
        help='Allow backdating of stock pickings'
    )
    
    backdate_enable_statement = fields.Boolean(
        string='Enable Bank Statement Backdating',
        default=True,
        config_parameter='sh_all_in_one_backdate.backdate_enable_statement',
        help='Allow backdating of bank statements'
    )
    
    backdate_log_retention_days = fields.Integer(
        string='Log Retention Days',
        default=365,
        config_parameter='sh_all_in_one_backdate.log_retention_days',
        help='Number of days to keep backdate logs (0 = keep forever)'
    )