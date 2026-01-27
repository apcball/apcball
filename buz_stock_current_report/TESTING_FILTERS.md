# Testing Instructions for Export Filter Implementation

## Pre-Testing Checklist

Before testing, ensure the following:
- [ ] Odoo 17 instance is running
- [ ] `report_xlsx` module is installed
- [ ] `buz_stock_current_report` module is installed/updated
- [ ] At least one internal stock location exists
- [ ] At least one product with stock exists
- [ ] At least one product category is created

## Module Installation/Update

```bash
# Navigate to Odoo custom addons directory
cd /opt/instance1/odoo17/custom-addons

# Update the module (if already installed)
python -m odoo -c /etc/odoo/odoo.conf -i buz_stock_current_report -u buz_stock_current_report --stop-after-init
```

## Test Cases

### Test 1: Basic Functionality - No Filters
**Objective**: Verify export works with date range only

**Steps**:
1. Go to **Inventory** > **Reports** > **Export Current Stock to Excel**
2. Set **Date From**: 2024-11-01
3. Set **Date To**: 2024-11-30
4. Leave all filters empty
5. Click **Export Excel**

**Expected Result**:
- Excel file downloads
- Filter section shows "All internal locations", "All products", "All categories"
- Report includes all products in all internal locations
- Data includes proper formatting (numbers with decimals, proper column widths)

---

### Test 2: Location Filter
**Objective**: Verify location filtering works correctly

**Steps**:
1. Go to **Inventory** > **Reports** > **Export Current Stock to Excel**
2. Set **Date From**: 2024-11-01
3. Set **Date To**: 2024-11-30
4. Select one or more locations in **Locations** field
5. Leave Products and Categories empty
6. Click **Export Excel**

**Expected Result**:
- Excel shows selected locations in filter section
- Report only contains products from selected locations
- Other locations are excluded

---

### Test 3: Product Filter
**Objective**: Verify product filtering works correctly

**Steps**:
1. Go to **Inventory** > **Reports** > **Export Current Stock to Excel**
2. Set **Date From**: 2024-11-01
3. Set **Date To**: 2024-11-30
4. Select specific products in **Products** field (e.g., 2-3 products)
5. Leave Locations and Categories empty
6. Click **Export Excel**

**Expected Result**:
- Excel shows selected products in filter section
- Report only contains selected products
- Products appear across all internal locations where they exist
- Other products are excluded

---

### Test 4: Category Filter
**Objective**: Verify product category filtering works correctly

**Steps**:
1. Go to **Inventory** > **Reports** > **Export Current Stock to Excel**
2. Set **Date From**: 2024-11-01
3. Set **Date To**: 2024-11-30
4. Select one or more product categories in **Product Categories** field
5. Leave Locations and Products empty
6. Click **Export Excel**

**Expected Result**:
- Excel shows selected categories in filter section
- Report only contains products belonging to selected categories
- Products appear across all internal locations where they exist
- Other categories are excluded

---

### Test 5: Combined Filters
**Objective**: Verify multiple filters work together (AND logic)

**Steps**:
1. Go to **Inventory** > **Reports** > **Export Current Stock to Excel**
2. Set **Date From**: 2024-11-01
3. Set **Date To**: 2024-11-30
4. Select **Locations**: Warehouse A
5. Select **Products**: Product X, Product Y
6. Select **Categories**: Electronics
7. Click **Export Excel**

**Expected Result**:
- Excel shows all applied filters
- Report shows only:
  - Products in Warehouse A
  - AND Product X or Product Y
  - AND belonging to Electronics category
- If no products match all criteria, report shows empty data with correct headers

---

### Test 6: Date Range Effect
**Objective**: Verify date range affects incoming/outgoing calculations

**Steps**:
1. Create stock movements with specific dates
2. Export with **Date From**: 2024-11-01, **Date To**: 2024-11-30
3. Export again with **Date From**: 2024-11-15, **Date To**: 2024-11-20
4. Compare results

**Expected Result**:
- Incoming/Outgoing quantities change based on date range
- Different date ranges produce different results
- Quantities reflect only movements within the specified date range

---

### Test 7: Excel Format Verification
**Objective**: Verify Excel file structure and formatting

**Steps**:
1. Export a report with some data
2. Open the Excel file
3. Verify:

**Expected Result**:
- Row 1: "Stock Report Filters" header (bold)
- Rows 2-7: Filter information (Date From, Date To, Locations, Products, Categories)
- Row 8: Empty row
- Row 9: Column headers (Location, Product, Category, Qty On Hand, Free to Use, Incoming, Outgoing, Unit Cost, Total Value, UoM) with gray background
- Row 10+: Data rows with:
  - Text columns left-aligned
  - Numeric columns formatted with 2 decimals
  - Proper column widths for readability
- Last data row + 2: Total Value summary row

---

### Test 8: Empty Data Scenario
**Objective**: Verify behavior when no data matches filters

**Steps**:
1. Select filters that result in no data:
   - E.g., select a specific product that has no stock
2. Click **Export Excel**

**Expected Result**:
- Excel file still generates
- Filter section displays correctly
- Headers are present
- No data rows (which is correct)
- No error messages

---

### Test 9: Large Dataset Performance
**Objective**: Verify export works with large amounts of data

**Steps**:
1. If you have test data with many products and locations:
2. Export without filters (or with minimal filters) for entire year
3. Measure time to generate

**Expected Result**:
- Export completes within reasonable time (< 30 seconds)
- All data is included
- File is readable in Excel (even with 10,000+ rows)

---

### Test 10: User Permissions
**Objective**: Verify only authorized users can export

**Steps**:
1. As admin user, export a report ✓
2. Create a test user with limited permissions
3. Log in as test user
4. Try to access Export Report

**Expected Result**:
- Admin can export successfully
- Limited users see appropriate permission errors or restricted data

---

## Debugging Tips

### If Export Button Doesn't Work
```python
# Check logs for errors
tail -f /var/log/odoo/odoo-server.log | grep -i "export\|error"

# Verify the model is properly installed
python -m odoo -c /etc/odoo/odoo.conf shell
>>> self.env['stock.current.export.wizard']
# Should return <class>
```

### If Excel File Is Empty
- Verify stock data exists: Go to **Inventory** > **Stock** > **Locations**
- Verify products have quantities assigned
- Check if filters are too restrictive

### If Filters Don't Appear
- Clear browser cache
- Reload the module
- Check `stock_current_export_wizard_views.xml` is valid XML

### If Numbers Are Incorrect
- Verify stock quantities in **Inventory** > **Stock**
- Check if date range includes the relevant movements
- Verify unit costs are set on products

## Logging Output

Check for relevant logs:

```bash
# Successful export should show:
Exporting stock report with filters - Date: 2024-11-01 to 2024-11-30
Successfully generated Excel export action
Generating Current Stock Excel Report with filters
Retrieved X filtered stock records
Successfully completed Excel report generation

# Error exports will show:
Error generating Excel export: [error details]
```

## Rollback Instructions

If you need to revert to the original version:

```bash
# Restore from version control if available
git checkout wizard/stock_current_export_wizard.py
git checkout views/stock_current_export_wizard_views.xml
git checkout report/stock_current_report_xlsx.py

# Restart Odoo
sudo systemctl restart instance1
```

## Post-Testing Sign-off

After completing all tests, verify:
- [ ] All test cases passed
- [ ] No error messages in logs
- [ ] Excel files open correctly
- [ ] Data is accurate
- [ ] Performance is acceptable
- [ ] User experience is intuitive
