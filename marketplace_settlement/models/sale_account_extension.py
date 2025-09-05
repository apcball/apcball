from odoo import models, fields, api, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    trade_channel = fields.Selection([('shopee', 'Shopee'), ('lazada', 'Lazada'), ('nocnoc', 'Noc Noc'), ('tiktok', 'Tiktok'), ('spx', 'SPX'), ('other', 'Other')], string='Trade Channel')

    def _prepare_invoice(self):
        """Extend invoice preparation to copy trade_channel from the sale order.

        This ensures invoices created from sale orders carry the same channel
        so the settlement wizard can filter by it.
        """
        vals = super()._prepare_invoice()
        # Some flows may create invoices for multiple orders; use order's value.
        vals['trade_channel'] = self.trade_channel
        return vals


class AccountMove(models.Model):
    _inherit = 'account.move'

    trade_channel = fields.Selection([('shopee', 'Shopee'), ('lazada', 'Lazada'), ('nocnoc', 'Noc Noc'), ('tiktok', 'Tiktok'), ('spx', 'SPX'), ('other', 'Other')], string='Trade Channel')
    is_refund = fields.Boolean('Is Credit Note', compute='_compute_is_refund')
    is_settled = fields.Boolean('Settled in Marketplace', compute='_compute_settlement_status', 
                               help='Indicates if this invoice is included in a posted marketplace settlement')
    settlement_ids = fields.Many2many('marketplace.settlement', string='Marketplace Settlements',
                                     help='Marketplace settlements that include this invoice')
    settlement_count = fields.Integer('Settlement Count', compute='_compute_settlement_status')
    settlement_ref = fields.Char('Settlement Reference', help='Reference to marketplace settlement for vendor bills')
    
    # Direct link from vendor bills to settlement for netting
    x_settlement_id = fields.Many2one('marketplace.settlement', 
                                     string='Marketplace Settlement',
                                     domain="[('company_id','=',company_id), ('marketplace_partner_id','=',partner_id)]",
                                     help='Link bill to settlement for netting')
    can_link_to_settlement = fields.Boolean('Can Link to Settlement', compute='_compute_can_link_to_settlement',
                                           help='Indicates if this vendor bill can be linked to a settlement')
    linked_settlement_state = fields.Selection(related='x_settlement_id.state', string='Settlement State', readonly=True)

    def _compute_is_refund(self):
        for rec in self:
            rec.is_refund = (rec.move_type == 'out_refund')

    @api.depends('move_type', 'state', 'partner_id')
    def _compute_can_link_to_settlement(self):
        """Determine if this vendor bill can be linked to a settlement"""
        for record in self:
            record.can_link_to_settlement = (
                record.move_type in ('in_invoice', 'in_refund') and
                record.state == 'posted' and
                record.partner_id and
                record.amount_residual > 0
            )

    @api.depends('settlement_ids', 'settlement_ids.state')
    def _compute_settlement_status(self):
        for record in self:
            posted_settlements = record.settlement_ids.filtered(lambda s: s.state == 'posted')
            record.is_settled = bool(posted_settlements)
            record.settlement_count = len(record.settlement_ids)

    def action_view_settlements(self):
        """View settlements that include this invoice"""
        self.ensure_one()
        
        if not self.settlement_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Settlements'),
                    'message': _('This invoice is not included in any marketplace settlement.'),
                    'type': 'info',
                }
            }
        
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Marketplace Settlements'),
            'res_model': 'marketplace.settlement',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.settlement_ids.ids)],
            'context': {
                'default_trade_channel': self.trade_channel,
            },
        }
        
        if len(self.settlement_ids) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': self.settlement_ids[0].id,
            })
        
        return action

    def action_link_to_settlement(self):
        """Open wizard to link vendor bill to settlement"""
        self.ensure_one()
        
        if not self.can_link_to_settlement:
            raise UserError(_('This bill cannot be linked to a settlement. Please ensure it is a posted vendor bill with outstanding amount.'))
            
        return {
            'type': 'ir.actions.act_window',
            'name': _('Link to Settlement'),
            'res_model': 'bill.link.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_vendor_bill_id': self.id,
                'default_partner_id': self.partner_id.id,
            },
        }

    def action_view_linked_settlement(self):
        """View the linked settlement"""
        self.ensure_one()
        
        if not self.x_settlement_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Settlement'),
                    'message': _('This vendor bill is not linked to any settlement.'),
                    'type': 'info',
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Linked Settlement'),
            'res_model': 'marketplace.settlement',
            'view_mode': 'form',
            'res_id': self.x_settlement_id.id,
        }
