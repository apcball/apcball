from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MarketplaceConfigChangeWizard(models.TransientModel):
    _name = 'marketplace.config.change.wizard'
    _description = 'Marketplace Configuration Change Wizard'

    vendor_bill_id = fields.Many2one('marketplace.vendor.bill', string='Vendor Bill', required=True)
    use_manual_config = fields.Boolean('Use Manual Configuration')
    keep_existing_lines = fields.Boolean('Keep Existing Lines', default=False,
                                       help='Keep existing lines when changing configuration')
    
    message = fields.Html('Message', default=lambda self: self._get_default_message())

    def _get_default_message(self):
        return """
        <p>You are changing the configuration mode for this vendor bill.</p>
        <p><strong>Options:</strong></p>
        <ul>
            <li><strong>Keep Existing Lines:</strong> Your current line items will be preserved but tax rates may be updated</li>
            <li><strong>Replace Lines:</strong> Current lines will be deleted and new default lines will be added based on the new configuration</li>
        </ul>
        """

    def action_apply_changes(self):
        """Apply configuration changes"""
        self.ensure_one()
        vendor_bill = self.vendor_bill_id
        
        if not self.keep_existing_lines:
            # Delete existing lines
            vendor_bill.line_ids.unlink()
            
            # Add new default lines based on configuration
            if vendor_bill.use_manual_config:
                vendor_bill._add_manual_default_lines()
            else:
                vendor_bill._add_profile_default_lines()
        else:
            # Update existing lines with new rates
            for line in vendor_bill.line_ids:
                if vendor_bill.use_manual_config:
                    line.vat_rate = vendor_bill.manual_vat_rate
                    line.wht_rate = vendor_bill.manual_wht_rate
                elif vendor_bill.profile_id:
                    line.vat_rate = vendor_bill.profile_id.default_vat_rate
                    line.wht_rate = vendor_bill.profile_id.default_wht_rate
        
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        """Cancel changes and revert configuration"""
        self.ensure_one()
        # Revert the configuration change
        self.vendor_bill_id.use_manual_config = not self.vendor_bill_id.use_manual_config
        return {'type': 'ir.actions.act_window_close'}
