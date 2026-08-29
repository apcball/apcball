# -*- coding: utf-8 -*-
"""Clean up after the Recalculate Valuation wizard.

Its work moved into fifo.recalculation.wizard in stock_fifo_by_warehouse_recal,
which does the same repairs with a preview, a mandatory backup and a rollback.

Odoo removes the module's own menu, action and ACL rows when they disappear from
the data files, but the transient model's table is left behind, and the group
that gated the wizard keeps whatever members it had while now granting nothing.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # The m2m relation table holds a foreign key onto the wizard table, so it
    # has to go first; a bare DROP on the wizard raises DependentObjectsStillExist.
    cr.execute("DROP TABLE IF EXISTS "
               "stock_valuation_recalculate_wizard_stock_warehouse_rel")
    cr.execute("DROP TABLE IF EXISTS stock_valuation_recalculate_wizard")
    _logger.info('dropped stock_valuation_recalculate_wizard and its m2m table')

    # Empty the obsolete group rather than deleting it: dropping a res.groups
    # row cascades into rules and menus that may reference it, and the record is
    # still declared (renamed) in security.xml.
    #
    # Checked on MOG_LIVE before this ran: the group had one member, uid 2, who
    # already holds stock_fifo_by_warehouse_recal.group_fifo_recalculation. So
    # nobody loses access they still need. Re-check before running this
    # anywhere else.
    cr.execute("""
        DELETE FROM res_groups_users_rel
        WHERE gid IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'stock_fifo_by_location'
              AND model = 'res.groups'
              AND name = 'group_stock_valuation_repair'
        )
    """)
    _logger.info('cleared %s members from the obsolete Stock Valuation Repair '
                 'group', cr.rowcount)
