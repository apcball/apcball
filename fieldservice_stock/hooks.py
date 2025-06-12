# Copyright (C) 2022 - OCA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import SUPERUSER_ID, api


def _pre_init_hook(env):
    cr = env.cr
    # Get the id of stock_location_customers using SQL instead of env.ref
    cr.execute(
        """
        SELECT res_id FROM ir_model_data
        WHERE module = 'stock' AND name = 'stock_location_customers'
        """
    )
    result = cr.fetchone()
    default_location_id = result[0] if result else None

    cr.execute(
        """
        ALTER TABLE
            fsm_location
        ADD COLUMN IF NOT EXISTS
            inventory_location_id INTEGER;
        """
    )

    if default_location_id:
        cr.execute(
            """UPDATE fsm_location SET inventory_location_id=%s;""", (default_location_id,)
        )
