from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kanban_location_ids = fields.Many2many(
        'stock.location',
        string='Kanban Display Locations',
        domain=[('usage', '=', 'internal')]
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        params = self.env['ir.config_parameter'].sudo()
        location_ids_str = params.get_param('buz_customize_kanban.kanban_location_ids', default='')
        
        if location_ids_str:
            location_ids = [int(id) for id in location_ids_str.split(',') if id.strip()]
        else:
            location_ids = []
        
        res.update(kanban_location_ids=[(6, 0, location_ids)])
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        params = self.env['ir.config_parameter'].sudo()
        
        if self.kanban_location_ids:
            location_ids_str = ','.join(map(str, self.kanban_location_ids.ids))
        else:
            location_ids_str = ''
        
        params.set_param('buz_customize_kanban.kanban_location_ids', location_ids_str)
