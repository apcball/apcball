# Biz Web List Column Order

Reorder list-view columns by **dragging their header** with the mouse. Each
user's chosen order is remembered independently, so one person's layout never
affects anyone else.

## Purpose

Odoo 17 Community lets you show/hide *optional* columns (the ⚙️ menu) but does
**not** let you change the left-to-right order of columns from the UI. This
module adds that, per user, for every backend list view.

## Dependencies

- `web`

## Features

- Drag a column header left/right to move it; a drop indicator shows where it
  will land.
- **Resize a column** (drag its right edge) and that column's width is
  remembered too.
- **Reset column layout** entry in the ⚙️ (optional columns) dropdown restores
  the default order and widths for the current list.
- Both the order and the widths are saved in the browser's `localStorage`,
  namespaced by the list view's resModel + view id, so each list keeps its own
  layout.
- Because storage is per-browser/per-user, it is inherently per-user and does
  not touch the shared view definition.
- Reordering and resizing don't interfere: dragging the header body reorders,
  dragging the right edge resizes.

## Post-install configuration

None. Works automatically on all backend list views once installed.

## Notes / limitations

- Order is stored per browser profile (localStorage). A user who switches
  browser or clears site data returns to the default order.
- Selector, handle, button and the actions/optional-columns cells are never
  reordered — only real field columns are draggable.
- The "Reset column layout" menu entry lives in the ⚙️ dropdown, so it is only
  reachable on lists that have at least one optional column. Other lists can
  still be reset by clearing the browser's site data.
