from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    x_planned_start = fields.Datetime(string="Planned Start")
    x_planned_end = fields.Datetime(string="Planned End")
