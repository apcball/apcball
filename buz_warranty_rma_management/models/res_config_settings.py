# Part of buz_warranty_rma_management Odoo module.
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # RMA settings
    buz_default_rma_in_type_id = fields.Many2one(
        'stock.picking.type',
        string='Default RMA Inbound Operation Type',
        config_parameter='buz.default_rma_in_type_id'
    )
    buz_default_rma_return_type_id = fields.Many2one(
        'stock.picking.type',
        string='Default RMA Return Operation Type',
        config_parameter='buz.default_rma_return_type_id'
    )
    buz_default_replacement_type_id = fields.Many2one(
        'stock.picking.type',
        string='Default Replacement Operation Type',
        config_parameter='buz.default_replacement_type_id'
    )
    buz_default_repair_location_id = fields.Many2one(
        'stock.location',
        string='Default Repair Location',
        config_parameter='buz.default_repair_location_id'
    )
    buz_reminder_days_before_expiry = fields.Integer(
        string='Days Before Expiry to Send Reminder',
        config_parameter='buz.reminder_days_before_expiry',
        default=7
    )