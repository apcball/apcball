# Module: stock_unreserve_manager (Odoo 17)

## Objective
Allow users to cancel stock reservations at picking, product, and global levels without breaking stock integrity.

---

## Features

### 1. Picking Unreserve
- Add button `action_unreserve_picking` on stock.picking
- Only works for state:
  - assigned
  - partially_available
- Use:
  move_ids._do_unreserve()

---

### 2. Force Unreserve
- Button: action_force_unreserve
- Reset move state to 'confirmed'
- Ignore downstream reservation conflicts

---

### 3. Bulk Unreserve Wizard
Model: stock.unreserve.wizard

Fields:
- unreserve_type: selection (picking, product, all)
- picking_ids: many2many
- product_ids: many2many
- location_id: many2one
- force: boolean

Methods:
- execute_unreserve()

---

### 4. Logging
Model: stock.unreserve.log

Fields:
- user_id
- datetime
- picking_id
- product_id
- qty
- reason
- type

---

### 5. Security
Group:
- stock_unreserve_manager.group_unreserve_manager

Rules:
- Only manager can force unreserve
- Only manager can bulk unreserve

---

### 6. UI
- Add buttons in stock.picking form
- Add server action for list view
- Add menu:
  Inventory > Operations > Unreserve Manager

---

## Constraints

- DO NOT delete stock.move
- DO NOT alter done quantities
- MUST preserve stock.move.line integrity

---

## Optional Enhancements

- Auto reassign after unreserve
- Reservation priority engine
- Aging dashboard
