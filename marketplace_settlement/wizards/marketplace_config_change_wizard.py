from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MarketplaceConfigChangeWizard(models.TransientModel):
    _name = 'marketplace.config.change.wizard'
    _description = 'Marketplace Configuration Change Wizard'

    vendor_bill_id = fields.Many2one('marketplace.vendor.bill', string='Vendor Bill', required=True)
    use_manual_config = fields.Boolean('Use Manual Configuration', readonly=True)
    keep_existing_lines = fields.Boolean('Keep Existing Lines', default=True,
                                       help='Keep existing lines and update rates only, otherwise replace all lines')
    message = fields.Text('Message', readonly=True, 
                        default='You are about to change the configuration mode. Choose whether to keep existing lines or replace them with new defaults.')

    def action_apply_changes(self):
        """Apply configuration changes"""
        self.ensure_one()
        vendor_bill = self.vendor_bill_id
        
        if not vendor_bill:
            raise UserError(_('No vendor bill specified'))
        
        if vendor_bill.state != 'draft':
            raise UserError(_('Can only change configuration for draft documents'))
        
        if self.keep_existing_lines:
            # Update existing lines with new rates
            for line in vendor_bill.line_ids:
                if vendor_bill.use_manual_config:
                    line.vat_rate = vendor_bill.manual_vat_rate
                    line.wht_rate = vendor_bill.manual_wht_rate
                elif vendor_bill.profile_id:
                    line.vat_rate = vendor_bill.profile_id.default_vat_rate
                    line.wht_rate = vendor_bill.profile_id.default_wht_rate
        else:
            # Replace all lines with new defaults
            vendor_bill.line_ids.unlink()
            if vendor_bill.use_manual_config:
                vendor_bill._add_manual_default_lines()
            elif vendor_bill.profile_id:
                vendor_bill._add_profile_default_lines()
        
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        """Cancel configuration change"""
        # Revert the configuration change
        vendor_bill = self.vendor_bill_id
        vendor_bill.use_manual_config = not vendor_bill.use_manual_config
        return {'type': 'ir.actions.act_window_close'}
