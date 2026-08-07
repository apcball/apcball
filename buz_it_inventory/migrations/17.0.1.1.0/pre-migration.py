


def migrate(cr, version):
    if not version:
        return



    _rename_table(cr, 'buz_it_consumable', 'buz_it_inventory_item')
    _rename_table(
        cr,
        'buz_it_consumable_category',
        'buz_it_inventory_item_category',
    )
    _rename_column(cr, 'buz_it_stock_quant', 'consumable_id', 'inventory_item_id')
    _rename_constraint(cr, 'buz_it_stock_quant', 'consumable_location_uniq', 'inventory_item_location_uniq')
    _rename_column(
        cr,
        'buz_it_stock_history',
        'consumable_id',
        'inventory_item_id',
    )

    cr.execute(
        """
        UPDATE ir_model
           SET model = 'buz.it.inventory.item'
         WHERE model = 'buz.it.consumable'
        """
    )
    cr.execute(
        """
        UPDATE ir_model
           SET model = 'buz.it.inventory.item.category'
         WHERE model = 'buz.it.consumable.category'
        """
    )
    cr.execute(
        """
        UPDATE ir_model_fields
           SET model = 'buz.it.inventory.item'
         WHERE model = 'buz.it.consumable'
        """
    )
    cr.execute(
        """
        UPDATE ir_model_fields
           SET model = 'buz.it.inventory.item.category'
         WHERE model = 'buz.it.consumable.category'
        """
    )
    cr.execute(
        """
        UPDATE ir_model_fields
           SET name = 'inventory_item_id'
         WHERE name = 'consumable_id'
           AND model IN (
               'buz.it.stock.quant',
               'buz.it.stock.history',
               'buz.it.stock.receive.line',
               'buz.it.stock.adjust.wizard'
           )
        """
    )
    cr.execute(
        """
        UPDATE ir_model_fields
           SET name = 'inventory_item_ids'
         WHERE model = 'buz.it.inventory.item.category'
           AND name = 'consumable_ids'
        """
    )
    cr.execute(
        """
        UPDATE ir_model_fields
           SET relation = 'buz.it.inventory.item'
         WHERE relation = 'buz.it.consumable'
        """
    )
    cr.execute(
        """
        UPDATE ir_model_fields
           SET relation = 'buz.it.inventory.item.category'
         WHERE relation = 'buz.it.consumable.category'
        """
    )

    for old_name, new_name in _XMLID_RENAMES.items():
        cr.execute(
            """
            UPDATE ir_model_data
               SET name = %s
             WHERE module = 'buz_it_inventory' AND name = %s
            """,
            (new_name, old_name),
        )


def _rename_table(cr, old_name, new_name):
    cr.execute(
        "SELECT to_regclass(%s)",
        (old_name,),
    )
    if cr.fetchone()[0]:
        cr.execute('ALTER TABLE "%s" RENAME TO "%s"' % (old_name, new_name))


def _rename_constraint(cr, table_name, old_name, new_name):
    cr.execute(
        """
        SELECT 1
          FROM pg_constraint constraint_row
          JOIN pg_class table_row ON table_row.oid = constraint_row.conrelid
         WHERE table_row.relname = %s
           AND constraint_row.conname = %s
        """,
        (table_name, old_name),
    )
    if cr.fetchone():
        cr.execute(
            'ALTER TABLE "%s" RENAME CONSTRAINT "%s" TO "%s"'
            % (table_name, old_name, new_name)
        )

def _rename_column(cr, table_name, old_name, new_name):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
        """,
        (table_name, old_name),
    )
    if cr.fetchone():
        cr.execute(
            'ALTER TABLE "%s" RENAME COLUMN "%s" TO "%s"'
            % (table_name, old_name, new_name)
        )


_XMLID_RENAMES = {
    'model_buz_it_consumable': 'model_buz_it_inventory_item',
    'model_buz_it_consumable_category': 'model_buz_it_inventory_item_category',
    'view_consumable_search': 'view_inventory_item_search',
    'view_consumable_tree': 'view_inventory_item_tree',
    'view_consumable_form': 'view_inventory_item_form',
    'view_consumable_category_tree': 'view_inventory_item_category_tree',
    'view_consumable_category_form': 'view_inventory_item_category_form',
    'action_consumable_items': 'action_inventory_items',
    'action_consumable_categories': 'action_inventory_item_categories',
    'action_consumable_quants': 'action_inventory_item_quants',
    'menu_consumable_stock': 'menu_inventory_stock',
    'menu_consumable_receive': 'menu_inventory_receive',
    'menu_consumable_adjust': 'menu_inventory_adjust',
    'menu_consumable_onhand': 'menu_inventory_onhand',
    'menu_consumable_locations': 'menu_inventory_locations',
    'menu_consumable_history': 'menu_inventory_history',
    'menu_consumable_config': 'menu_inventory_config',
    'menu_consumable_items': 'menu_inventory_items',
    'menu_consumable_categories': 'menu_inventory_item_categories',
    'rule_consumable_company': 'rule_inventory_item_company',
    'rule_consumable_requester_published': 'rule_inventory_item_requester_published',
    'rule_consumable_it_all': 'rule_inventory_item_it_all',
    'access_consumable_requester': 'access_inventory_item_requester',
    'access_consumable_agent': 'access_inventory_item_agent',
    'access_consumable_manager': 'access_inventory_item_manager',
    'access_consumable_category_requester': 'access_inventory_item_category_requester',
    'access_consumable_category_manager': 'access_inventory_item_category_manager',
}
