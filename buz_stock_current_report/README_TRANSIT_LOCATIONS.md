# Transit Locations in Warehouse Sidebar

## Overview
This enhancement adds support for displaying transit locations in the Current Stock View sidebar, organized as a separate section for each warehouse.

## Changes Made

### 1. Python Model (`models/stock_current_report.py`)
- Created new method `get_warehouses_with_locations()` to replace `get_warehouses_with_internal_locations()`
- Added separate queries for internal and transit locations
- Returns warehouse data with two location arrays: `internal_locations` and `transit_locations`
- Maintained backward compatibility with existing `locations` field

### 2. JavaScript Component (`static/src/js/stock_current_report.js`)
- Updated `loadWarehouses()` to call the new method
- Added new controller classes for views with sidebar
- Registered new view types: `stock_current_list_sidebar` and `stock_current_kanban_sidebar`
- Added necessary imports for renderers

### 3. XML Templates (`static/src/xml/stock_current_report.xml`)
- Modified `WarehouseSidebar` template to display internal and transit locations separately
- Added section headers with appropriate icons
- Used different badge colors for transit locations (warning/yellow)
- Created new templates for views with sidebar: `ListWithSidebar` and `KanbanWithSidebar`

### 4. CSS Styling (`static/src/css/stock_current_report.css`)
- Added comprehensive styling for warehouse sidebar
- Created distinct styling for transit locations section
- Added hover effects and transitions
- Included responsive design adjustments

### 5. View Definitions (`views/stock_current_report_sidebar_views.xml`)
- Updated view definitions to use new sidebar view classes
- Ensured proper integration with the sidebar component

## Features

### Visual Distinctions
- **Internal Locations**: Blue badges, home icon, standard styling
- **Transit Locations**: Yellow/warning badges, exchange-alt icon, left border highlight

### Functionality
- Expandable warehouse sections
- Click to filter by specific location
- Search functionality across all location types
- Summary statistics for each warehouse
- Responsive design for mobile devices

## Usage

1. Navigate to **Inventory → Current Stock Report → Current Stock View**
2. Expand any warehouse to see both internal and transit locations
3. Click on any location to filter the stock report
4. Use the search box to find specific locations
5. Toggle "Show only with stock" to hide empty locations

## Testing

Run the test script to verify the implementation:
```bash
python buz_stock_current_report/test_transit_locations.py
```

## Backward Compatibility

The old `get_warehouses_with_internal_locations()` method is maintained as a wrapper around the new method, ensuring existing code continues to work.

## Notes

- Transit locations are identified by `usage = 'transit'` in the stock_location table
- Only active locations are displayed (`active = true`)
- The sidebar automatically refreshes when data changes
- All location types support the same filtering and search functionality