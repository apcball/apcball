# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def _auto_init(self):
        """
        Override _auto_init to set decimal places automatically on module install.
        This method is called during module installation/upgrade.
        Only works for currencies not yet used in accounting entries.
        """
        # Call parent _auto_init first
        res = super(ResCurrency, self)._auto_init()
        
        # Try to set decimal places for THB currency
        # This will only work if no accounting entries exist
        try:
            self._set_currency_decimal_places()
        except Exception as e:
            _logger.warning(
                "Could not automatically set THB decimal places. "
                "Currency may already be in use. Error: %s" % str(e)
            )
        
        return res

    @api.model
    def _set_currency_decimal_places(self):
        """
        Find THB currency and set decimal_places to 2 and rounding to 0.01
        Only updates if current decimal_places is greater than 2.
        """
        # Search for THB currency by name
        thb_currency = self.search([('name', '=', 'THB')], limit=1)
        
        if thb_currency:
            # Only update if current decimal places is greater than 2
            # to avoid the "cannot reduce" error
            if thb_currency.decimal_places > 2:
                _logger.info(
                    "Attempting to update THB currency from %s to 2 decimal places" 
                    % thb_currency.decimal_places
                )
                # Update decimal places and rounding
                thb_currency.write({
                    'decimal_places': 2,
                    'rounding': 0.01,
                })
                _logger.info("THB currency updated successfully")
            else:
                _logger.info(
                    "THB currency already has %s decimal places, no update needed" 
                    % thb_currency.decimal_places
                )
    
    def action_force_update_decimal_places(self):
        """
        Manual action to force update decimal places.
        WARNING: This should only be used on fresh databases or after careful consideration.
        Use this from the Technical menu if automatic update failed.
        """
        for currency in self:
            if currency.name == 'THB':
                try:
                    # Direct SQL update to bypass Odoo constraints
                    self.env.cr.execute("""
                        UPDATE res_currency 
                        SET decimal_places = 2, rounding = 0.01
                        WHERE id = %s
                    """, (currency.id,))
                    _logger.info("Force updated THB currency decimal places via SQL")
                except Exception as e:
                    raise UserError(_(
                        "Could not force update currency. "
                        "This currency may be used in accounting entries. Error: %s"
                    ) % str(e))
