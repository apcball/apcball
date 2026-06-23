# -*- coding: utf-8 -*-

from odoo import models, fields


class MarketplaceApiLog(models.Model):
    _name = 'buz.marketplace.api.log'
    _description = 'Marketplace API Log'
    _order = 'create_date desc'

    account_id = fields.Many2one(
        'buz.marketplace.account',
        string='Marketplace Account',
        index=True
    )
    endpoint = fields.Char(
        string='Endpoint',
        required=True,
        index=True
    )
    method = fields.Char(
        string='HTTP Method',
        default='POST'
    )
    request_headers = fields.Text(
        string='Request Headers'
    )
    request_body = fields.Text(
        string='Request Body'
    )
    response_status = fields.Integer(
        string='Response Status'
    )
    response_body = fields.Text(
        string='Response Body'
    )
    duration_ms = fields.Integer(
        string='Duration (ms)'
    )
    error_message = fields.Text(
        string='Error Message'
    )
    company_id = fields.Many2one(
        'res.company',
        related='account_id.company_id',
        store=True,
        index=True
    )
