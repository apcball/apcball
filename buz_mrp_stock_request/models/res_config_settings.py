from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    group_mrp_stock_request_user = fields.Boolean(
        string="MRP Stock Request",
        implied_group="buz_mrp_stock_request.group_mrp_stock_request_user",
    )
    stock_request_source_location_id = fields.Many2one(
        "stock.location",
        string="Stock Request Source Location",
        config_parameter="buz_mrp_stock_request.default_source_location_id",
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]",
    )
    stock_request_dest_location_id = fields.Many2one(
        "stock.location",
        string="Stock Request Destination Location",
        config_parameter="buz_mrp_stock_request.default_dest_location_id",
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]",
    )

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        # Set the config parameters
        self.env['ir.config_parameter'].sudo().set_param(
            'buz_mrp_stock_request.default_source_location_id', 
            self.stock_request_source_location_id.id
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'buz_mrp_stock_request.default_dest_location_id', 
            self.stock_request_dest_location_id.id
        )

    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        # Get the config parameters
        ICPSudo = self.env['ir.config_parameter'].sudo()
        source_location_param = ICPSudo.get_param('buz_mrp_stock_request.default_source_location_id')
        dest_location_param = ICPSudo.get_param('buz_mrp_stock_request.default_dest_location_id')
        
        # Convert to int, but only if the parameter exists and is not empty
        source_location_id = int(source_location_param) if source_location_param else False
        dest_location_id = int(dest_location_param) if dest_location_param else False
        
        # Validate that these IDs exist in the database before returning them
        if source_location_id:
            source_location = self.env['stock.location'].browse(source_location_id)
            if not source_location.exists():
                source_location_id = False

        if dest_location_id:
            dest_location = self.env['stock.location'].browse(dest_location_id)
            if not dest_location.exists():
                dest_location_id = False

        res.update(
            stock_request_source_location_id=source_location_id,
            stock_request_dest_location_id=dest_location_id,
        )
        return res