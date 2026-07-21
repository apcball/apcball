from odoo import fields, models


class BuzReservationReleaseReason(models.Model):
    _name = "buz.reservation.release.reason"
    _description = "Reservation Release Reason"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
