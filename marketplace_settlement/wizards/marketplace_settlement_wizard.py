from odoo import models, fields, api, _


class MarketplaceSettlementWizard(models.TransientModel):
    _name = 'marketplace.settlement.wizard'
    _description = 'Wizard to create marketplace settlement'

    name = fields.Char('Settlement Ref', required=True)
    marketplace_partner_id = fields.Many2one('res.partner', string='Marketplace Partner', required=True)
    journal_id = fields.Many2one('account.journal', string='Journal', required=True)
    date = fields.Date('Date', required=True)
    trade_channel = fields.Selection([('shopee', 'Shopee'), ('lazada', 'Lazada'), ('nocnoc', 'Noc Noc'), ('tiktok', 'Tiktok'), ('other', 'Other')], string='Trade Channel')
    invoice_ids = fields.Many2many('account.move', string='Invoices')

    @api.onchange('trade_channel')
    def _onchange_trade_channel(self):
        if self.trade_channel:
            return {'domain': {'invoice_ids': [('state', '=', 'posted'), ('move_type', 'in', ['out_invoice', 'out_refund']), ('trade_channel', '=', self.trade_channel), ('amount_residual', '!=', 0.0)]}}

    def action_create(self):
        self.ensure_one()
        settlement = self.env['marketplace.settlement'].create({
            'name': self.name,
            'marketplace_partner_id': self.marketplace_partner_id.id,
            'journal_id': self.journal_id.id,
            'date': self.date,
            'trade_channel': self.trade_channel,
            'invoice_ids': [(6, 0, self.invoice_ids.ids)],
        })
        settlement.action_create_settlement()
        return {'type': 'ir.actions.act_window_close'}
