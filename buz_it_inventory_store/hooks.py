_INVENTORY_XML_IDS = (
    'view_consumable_search', 'view_consumable_tree', 'view_consumable_form',
    'view_consumable_category_tree', 'view_consumable_category_form',
    'action_consumable_items', 'action_consumable_categories',
    'view_stock_location_tree', 'view_stock_location_form',
    'view_stock_quant_tree', 'view_stock_quant_search',
    'view_stock_history_tree', 'view_stock_history_search',
    'action_stock_location', 'action_consumable_quants', 'action_stock_history',
    'view_stock_receive_wizard_form', 'action_stock_receive',
    'view_stock_adjust_wizard_form', 'action_stock_adjust',
    'menu_consumable_stock', 'menu_consumable_receive', 'menu_consumable_adjust',
    'menu_consumable_onhand', 'menu_consumable_locations', 'menu_consumable_history',
    'menu_consumable_config', 'menu_consumable_items', 'menu_consumable_categories',
)


def pre_init_hook(env):
    env.cr.execute(
        """
        UPDATE ir_model_data
           SET module = 'buz_it_inventory_store'
         WHERE module = 'buz_it_consumable_store'
           AND name = ANY(%s)
        """,
        [list(_INVENTORY_XML_IDS)],
    )
