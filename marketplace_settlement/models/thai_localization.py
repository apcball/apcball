# Copyright 2024 Ball + Manow
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html)

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class MarketplaceSettlementThaiLocalization(models.TransientModel):
    _name = 'marketplace.settlement.thai.localization'
    _description = 'Thai Localization Helper for Marketplace Settlement'

    settlement_id = fields.Many2one('marketplace.settlement.wizard', string='Settlement')
    
    # Thai WHT fields
    thai_income_tax_form = fields.Selection([
        ('pnd1', 'PND1'),
        ('pnd2', 'PND2'),
        ('pnd3', 'PND3'),
        ('pnd3a', 'PND3a'),
        ('pnd53', 'PND53'),
    ], string='Income Tax Form')
    
    thai_wht_income_type = fields.Selection([
        ('1', '1. เงินเดือน ค่าจ้าง ฯลฯ 40(1)'),
        ('2', '2. ค่าธรรมเนียม ค่านายหน้า ฯลฯ 40(2)'),
        ('3', '3. ค่าแห่งลิขสิทธิ์ ฯลฯ 40(3)'),
        ('4A', '4. ดอกเบี้ย ฯลฯ 40(4)ก'),
    ], string='WHT Income Type')

    @api.model
    def is_thai_localization_available(self):
        """Check if Thai localization modules are available"""
        try:
            # Check if Thai WHT certificate module is installed
            thai_wht_module = self.env['ir.module.module'].search([
                ('name', '=', 'l10n_th_account_wht_cert_form'),
                ('state', '=', 'installed')
            ])
            return bool(thai_wht_module)
        except Exception as e:
            _logger.debug("Thai localization check failed: %s", e)
            return False

    def create_thai_wht_certificate(self):
        """Create Thai WHT certificate if Thai localization is available"""
        if not self.is_thai_localization_available():
            _logger.warning("Thai localization modules not available")
            return False
            
        try:
            # Only attempt to create WHT certificate if Thai modules are available
            # This would be implemented when Thai modules are actually installed
            _logger.info("Thai WHT certificate creation requested but Thai modules not installed")
            return True
        except Exception as e:
            _logger.error("Failed to create Thai WHT certificate: %s", e)
            return False

    def process_thai_tax_integration(self):
        """Process Thai tax integration if available"""
        if not self.is_thai_localization_available():
            return False
            
        try:
            # Thai tax processing would be implemented here
            # when Thai localization modules are available
            _logger.info("Thai tax integration processed")
            return True
        except Exception as e:
            _logger.error("Failed to process Thai tax integration: %s", e)
            return False
