from odoo import models, fields


class MarketplaceSettlementProfile(models.Model):
    _name = 'marketplace.settlement.profile'
    _description = 'Marketplace Settlement Profile per Channel'

    name = fields.Char('Profile Name', required=True)
    trade_channel = fields.Selection([
        ('shopee', 'Shopee'),
        ('lazada', 'Lazada'),
        ('nocnoc', 'Noc Noc'),
        ('tiktok', 'Tiktok'),
        ('other', 'Other'),
    ], string='Trade Channel', required=True)
    marketplace_partner_id = fields.Many2one('res.partner', string='Marketplace Partner')
    journal_id = fields.Many2one('account.journal', string='Default Journal')
    settlement_account_id = fields.Many2one('account.account', string='Default Settlement Account')
