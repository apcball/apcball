# Copyright 2020 Acsone SA/NV
# Copyright 2020 Camptocamp
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from itertools import groupby

from psycopg2 import sql

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):

    _inherit = "product.template"

    def write(self, vals):
        uom_id = vals.pop("uom_id", False)
        uom_po_id = vals.pop("uom_po_id", False)
        if uom_id:
            self._update_uom(uom_id, "uom_id")
        if uom_po_id:
            self._update_uom(uom_po_id, "uom_po_id")
        res = super().write(vals)
        return res

    def _update_uom(self, uom_id, field_name):
        uom_obj = self.env["uom.uom"]
        new_uom = uom_obj.browse(uom_id)
        
        _logger.info("Attempting to update UoM field %s to UoM ID %s (%s)", 
                     field_name, uom_id, new_uom.name if new_uom else 'Unknown')
        
        sorted_items = sorted(self, key=lambda r: r[field_name])
        for key, products_group in groupby(sorted_items, key=lambda r: r[field_name]):
            product_ids = [p.id for p in products_group]
            
            _logger.info("Processing products with current UoM: %s (ID: %s)", 
                         key.name if key else 'None', key.id if key else 'None')
            
            # Ensure both UoMs exist and have categories
            if not key or not new_uom or not key.category_id or not new_uom.category_id:
                _logger.error("Invalid UoM configuration - key: %s, new_uom: %s", key, new_uom)
                raise UserError(
                    _(
                        "Invalid unit of measure. Please ensure both current and new "
                        "units of measure are properly configured with categories."
                    )
                )
            
            _logger.info("Comparing categories: current=%s (%s) vs new=%s (%s)", 
                         key.category_id.name, key.category_id.id,
                         new_uom.category_id.name, new_uom.category_id.id)
            
            # Check if UoMs are in the same category
            if key.category_id.id == new_uom.category_id.id:
                _logger.info("Categories match, updating %d products", len(product_ids))
                # Use direct SQL update for performance
                query = sql.SQL(
                    "UPDATE product_template SET {field} = %s WHERE id in %s"
                ).format(field=sql.Identifier(field_name))
                self.env.cr.execute(query, (new_uom.id, tuple(product_ids)))
                products = self.env["product.template"].browse(product_ids)
                products.invalidate_recordset(fnames=[field_name])
                _logger.info("Successfully updated UoM for products: %s", product_ids)
            else:
                _logger.warning("Category mismatch: %s != %s", key.category_id.name, new_uom.category_id.name)
                # Provide more specific error message
                raise UserError(
                    _(
                        "You cannot change the unit of measure from '%s' (category: %s) "
                        "to '%s' (category: %s). Units must be in the same category."
                    ) % (
                        key.name, key.category_id.name,
                        new_uom.name, new_uom.category_id.name
                    )
                )
