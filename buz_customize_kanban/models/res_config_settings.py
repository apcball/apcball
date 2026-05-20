from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kanban_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Kanban Warehouse',
    )

    kanban_pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Kanban Pricelist',
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        params = self.env['ir.config_parameter'].sudo()
        warehouse_id = params.get_param('buz_customize_kanban.kanban_warehouse_id')
        pricelist_id = params.get_param('buz_customize_kanban.kanban_pricelist_id')
        res.update(
            kanban_warehouse_id=int(warehouse_id) if warehouse_id else False,
            kanban_pricelist_id=int(pricelist_id) if pricelist_id else False,
        )
        return res

    def set_values(self):
        super().set_values()
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('buz_customize_kanban.kanban_warehouse_id', self.kanban_warehouse_id.id or '')
        params.set_param('buz_customize_kanban.kanban_pricelist_id', self.kanban_pricelist_id.id or '')
