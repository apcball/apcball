from odoo import fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    external_request_id = fields.Char(
        string='External Request ID',
        index=True,
        copy=False,
    )

    _sql_constraints = [
        (
            'crm_lead_external_request_id_uniq',
            'unique(external_request_id)',
            'A CRM lead can only be imported once for an external request.',
        ),
    ]
