from odoo import models, fields, api, _
from odoo.exceptions import UserError


class BillLinkWizard(models.TransientModel):
    _name = 'bill.link.wizard'
    _description = 'Link Vendor Bill to Marketplace Document'

    marketplace_document_id = fields.Many2one('marketplace.vendor.bill', string='Marketplace Document', required=True)
    vendor_bill_id = fields.Many2one('account.move', string='Vendor Bill', required=True,
                                   domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'draft'), ('trade_channel', '=', trade_channel)]")
    trade_channel = fields.Selection(related='marketplace_document_id.trade_channel', string='Trade Channel', readonly=True)
    partner_id = fields.Many2one(related='marketplace_document_id.partner_id', string='Partner', readonly=True)
    document_reference = fields.Char(related='marketplace_document_id.document_reference', string='Document Reference', readonly=True)

    def action_link_bill(self):
        """Link the selected vendor bill to the marketplace document"""
        self.ensure_one()
        
        if not self.vendor_bill_id:
            raise UserError(_('Please select a vendor bill to link'))
        
        if self.vendor_bill_id.state != 'draft':
            raise UserError(_('Can only link draft vendor bills'))
        
        # Update the vendor bill with marketplace document information
        self.vendor_bill_id.write({
            'trade_channel': self.trade_channel,
            'settlement_ref': f'MP-{self.document_reference}',
            'ref': self.document_reference,
        })
        
        # Update the marketplace document
        self.marketplace_document_id.write({
            'vendor_bill_id': self.vendor_bill_id.id,
            'state': 'processed'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.vendor_bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
