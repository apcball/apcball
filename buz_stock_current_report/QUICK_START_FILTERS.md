# Export to Excel with Filters - Quick Start Guide

## Feature Overview
The enhanced `buz_stock_current_report` module now allows users to export stock reports to Excel with advanced filtering options.

## Available Filters

### 1. Date Range (Required)
- **Date From**: Start date for the report period
- **Date To**: End date for the report period
- Used to calculate incoming and outgoing movements

### 2. Location (Optional)
- Filter by specific warehouse or storage location
- Multiple locations can be selected
- Leave empty to include all internal locations

### 3. Product (Optional)
- Filter by specific products
- Multiple products can be selected
- Leave empty to include all products

### 4. Product Category (Optional)
- Filter by product category
- Multiple categories can be selected
- Leave empty to include all categories

## Excel Report Output

### Filter Summary Section
The first rows of the Excel report display:
- Date From & Date To
- Applied locations (or "All internal locations")
- Applied products (or "All products")
- Applied categories (or "All categories")

### Data Table
Columns included:
1. **Location** - Warehouse/Location name
2. **Product** - Product name
3. **Category** - Product category
4. **Qty On Hand** - Current quantity in stock
5. **Free to Use** - Available quantity (not reserved)
6. **Incoming** - Pending incoming stock
7. **Outgoing** - Pending outgoing stock
8. **Unit Cost** - Product unit cost
9. **Total Value** - Total inventory value (Qty × Unit Cost)
10. **UoM** - Unit of measure

### Summary Row
- Total Value sum at the bottom of the report

## Examples

### Example 1: Specific Location Only
- Date From: 2024-11-01
- Date To: 2024-11-30
- Location: Main Warehouse
- Products: (empty)
- Categories: (empty)
**Result**: All products in Main Warehouse for November

### Example 2: Specific Category and Location
- Date From: 2024-11-01
- Date To: 2024-11-30
- Location: Main Warehouse
- Products: (empty)
- Categories: Electronics
**Result**: All electronic products in Main Warehouse

### Example 3: Specific Products Only
- Date From: 2024-11-01
- Date To: 2024-11-30
- Location: (empty)
- Products: Product A, Product B, Product C
- Categories: (empty)
**Result**: Specific products in all internal locations

### Example 4: No Filters (except date range)
- Date From: 2024-11-01
- Date To: 2024-11-30
- Location: (empty)
- Products: (empty)
- Categories: (empty)
**Result**: All products in all internal locations

## How to Access

1. Go to **Inventory** menu
2. Select **Reports** → **Export Current Stock to Excel**
3. Configure desired filters
4. Click **Export Excel**
5. Excel file will be downloaded

## Filter Behavior

- **All filters are optional** (except date range)
- **Empty filters include all records** in that category
- **Multiple selections are AND/OR combinations**:
  - Within same filter type: OR logic (A OR B OR C)
  - Between different filter types: AND logic
- **Example**: Location=Warehouse1 AND Category=Electronics means all electronic products in Warehouse1

## Performance Notes

- Large date ranges with no filters may take longer to generate
- Using specific filters (location, product, category) improves export speed
- Typical export time: 1-5 seconds depending on data volume

## Troubleshooting

### Export Takes Too Long
- Reduce date range
- Add location or product filter to limit data

### Missing Data in Export
- Check that filters aren't too restrictive
- Verify date range includes the relevant period
- Ensure stock records exist for selected filters

### Empty Product/Location Dropdowns
- Verify internal locations exist in system
- Verify products are created and linked to categories
- Check user permissions for these models
