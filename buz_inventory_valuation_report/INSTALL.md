# Installation and Setup Guide

## Prerequisites

1. Odoo 17 Community or Enterprise Edition
2. Python xlsxwriter library (optional for Excel export)

```bash
pip install xlsxwriter
```

## Installation Steps

1. **Copy Module**: Copy the `buz_inventory_valuation_report` folder to your Odoo addons directory:
   ```
   /opt/instance1/odoo17/custom-addons/buz_inventory_valuation_report/
   ```

2. **Restart Odoo**: Restart your Odoo server to recognize the new module

3. **Update Apps List**: 
   - Go to Apps menu
   - Click on "Update Apps List"

4. **Install Module**:
   - Search for "BUZ Inventory Valuation Report"
   - Click Install

## Usage

1. Navigate to: **Inventory > Reporting > Inventory Valuation > Inventory Valuation PDF/XLS**

2. Configure your report:
   - Set date range (required)
   - Select warehouses (optional)
   - Select locations (optional) 
   - Select product categories (optional)
   - Select specific products (optional)
   - Choose report format (PDF or Excel)

3. Generate report using one of:
   - "Generate Report" button
   - "Print PDF" button
   - "Export Excel" button

## Features Available

✅ **Date Range Filtering**
✅ **Warehouse Filtering** 
✅ **Location Filtering**
✅ **Product Category Filtering**
✅ **Product Filtering**
✅ **PDF Export**
✅ **Excel Export**
✅ **Professional Layout**
✅ **Real-time Data**

## Troubleshooting

**Excel Export Issues:**
- If Excel export doesn't work, install xlsxwriter: `pip install xlsxwriter`
- Fallback CSV format will be used if xlsxwriter is not available

**No Data Showing:**
- Check date range covers period with stock movements
- Verify selected filters aren't too restrictive
- Ensure products have stock quantities

**Permission Issues:**
- Module requires Stock User or Stock Manager permissions
- Check user has access to Inventory > Reporting menu
