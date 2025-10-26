# Warranty Management Manual Creation Implementation Plan

## Overview
This document outlines the changes required to convert the warranty management module from automatic warranty card creation to manual creation via Sale Order.

## Changes Required

### 1. Sale Order Integration
**File to create:** `views/sale_order_views.xml`
- Add inheritance view for sale.order form
- Add "Create Warranty Card" button in the header
- Button should be visible when order has delivered products with warranty configuration
- Add smart button to show related warranty cards

**File to create:** `models/sale_order.py`
- Add method `action_create_warranty_card()` to handle warranty card creation
- Add method `action_view_warranty_cards()` to view related warranty cards
- Add computed field `warranty_card_count` for smart button
- Logic should check delivered products with warranty duration > 0

### 2. Product Template Modifications
**File to modify:** `views/product_template_views.xml`
- Remove `auto_warranty` checkbox field (line 15)
- Remove `invisible="auto_warranty == False"` conditions from warranty fields
- Make warranty duration fields always visible when warranty_duration > 0
- Keep all other warranty configuration fields

**File to modify:** `models/product_template.py`
- Remove `auto_warranty` field definition (lines 25-29)
- Update field visibility logic in views

### 3. Stock Picking Changes
**File to modify:** `models/stock_picking.py`
- Remove or comment out the automatic warranty card creation logic
- Remove the call to `_create_warranty_cards()` from `button_validate()` method
- Keep the model structure intact for potential future use

### 4. Warranty Card Model Updates
**File to modify:** `models/warranty_card.py`
- Ensure manual creation works properly from sale orders
- Add validation to ensure warranty cards are created with proper sale order reference
- No major changes needed as the model already supports manual creation

### 5. Module Description Update
**File to modify:** `__manifest__.py`
- Update description to reflect manual warranty creation
- Change line 10 from "Automatic warranty card creation on delivery" to "Manual warranty card creation from Sale Order"
- Update summary if needed

### 6. Update Manifest
**File to modify:** `__manifest__.py`
- Add new files to data list:
  - `views/sale_order_views.xml`
- Add new model to imports if needed

## Implementation Details

### Sale Order Button Logic
The "Create Warranty Card" button should:
1. Check if the sale order has delivered products
2. Filter products with warranty_duration > 0
3. Create warranty cards for each delivered product with serial/lot numbers
4. Show a wizard or notification with created warranty cards

### Product Form Changes
- Warranty duration fields should always be visible when warranty_duration > 0
- Remove dependency on auto_warranty checkbox
- Keep all warranty terms and conditions functionality

### Workflow Changes
1. User configures warranty on product (duration, terms, type)
2. Sale order is created and delivered
3. User clicks "Create Warranty Card" button on sale order
4. System creates warranty cards for delivered products with warranty
5. Warranty cards can be managed as before (claims, RMA, etc.)

## Testing Checklist
- [ ] Product form shows warranty fields without auto_warranty checkbox
- [ ] Sale order shows "Create Warranty Card" button for delivered orders
- [ ] Warranty cards are created correctly from sale order
- [ ] Warranty claims and RMA workflows still function
- [ ] Warranty certificates can be printed
- [ ] Dashboard shows correct warranty information

## Files to Modify
1. `__manifest__.py` - Update description and add new files
2. `views/product_template_views.xml` - Remove auto_warranty checkbox
3. `models/product_template.py` - Remove auto_warranty field
4. `models/stock_picking.py` - Remove automatic creation
5. `models/warranty_card.py` - Minor updates for manual creation

## Files to Create
1. `views/sale_order_views.xml` - Sale order view inheritance
2. `models/sale_order.py` - Sale order model methods