# User Guide: Quick Material Allocation

## Overview
This guide explains how to use the new "Allocate Materials" feature to quickly consume materials to your Manufacturing Orders.

## When to Use This Feature

Use the Quick Allocation feature when:
- ✅ Materials have already been issued via a Stock Request
- ✅ You're viewing a Manufacturing Order that needs materials
- ✅ You want to allocate materials quickly without navigating multiple screens

## Step-by-Step Guide

### Step 1: Open Your Manufacturing Order

Navigate to **Manufacturing → Operations → Manufacturing Orders** and open the MO that needs materials.

Example: `WH/MO/00025`

### Step 2: Look for the "Allocate Materials" Button

In the MO header (top of the form), you'll see an **"Allocate Materials"** button.

**Note**: This button only appears when materials are available to allocate.

**If you don't see the button**, it means:
- No stock requests are linked to this MO, OR
- Materials haven't been issued yet, OR
- All materials have already been allocated

### Step 3: Click "Allocate Materials"

A wizard window will open showing all available materials from linked stock requests.

### Step 4: Review the Available Materials

The wizard displays a table with:
- **Product**: The material to allocate
- **Available**: How much is available from the stock request
- **Qty to Consume**: How much you want to allocate (pre-filled)
- **UoM**: Unit of measure
- **Lot/Serial**: Lot or serial number (for tracked products)
- **Notes**: Optional notes for this allocation

### Step 5: Adjust Quantities (If Needed)

You can modify the quantities in the "Qty to Consume" column:

**To allocate the full amount**: Leave as-is (pre-filled with available quantity)

**To allocate partially**: Change the number to a smaller amount

**To skip allocation**: Set to `0`

**Example**:
```
Product A    Available: 10.0    To Consume: 10.0    ← Allocate all
Product B    Available: 5.0     To Consume: 3.0     ← Allocate 3 only
Product C    Available: 8.0     To Consume: 0       ← Skip for now
```

### Step 6: Add Lot/Serial Numbers (If Required)

For products tracked by lot or serial number:
1. The **Lot/Serial** field will automatically appear
2. Click the dropdown to select an existing lot
3. Or type to create a new lot number

**Important**: 
- For serial-tracked products, quantity must be `1.0` per serial
- For lot-tracked products, you can have any quantity with the same lot

### Step 7: Click "Allocate"

Click the blue **"Allocate"** button at the bottom.

The system will:
- ✓ Validate your entries
- ✓ Consume the materials to the MO
- ✓ Update the Components tab
- ✓ Create allocation records
- ✓ Log the allocation in the chatter
- ✓ Show a success notification

### Step 8: Verify the Allocation

After allocation:
1. The wizard closes automatically
2. A success message appears: "X material(s) allocated to [MO Name]"
3. Check the **Components** tab to see updated consumed quantities
4. Check the **Chatter** (bottom of MO form) for allocation details

## Common Scenarios

### Scenario 1: Simple Allocation (No Lot Tracking)

**Situation**: You need to allocate 10 units of Product A

**Steps**:
1. Open MO
2. Click "Allocate Materials"
3. See: Product A, Available: 10.0, To Consume: 10.0
4. Click "Allocate"
5. Done!

**Time**: ~5 seconds

---

### Scenario 2: Partial Allocation

**Situation**: Materials available but you only want to allocate some now

**Steps**:
1. Open MO
2. Click "Allocate Materials"
3. Change quantities:
   - Product A: Keep 10.0 (allocate all)
   - Product B: Change to 3.0 (allocate 3 of 5 available)
   - Product C: Change to 0 (skip)
4. Click "Allocate"
5. Products A and B allocated, Product C remains available for later

**Time**: ~15 seconds

---

### Scenario 3: Lot-Tracked Products

**Situation**: Allocating products that require lot numbers

**Steps**:
1. Open MO
2. Click "Allocate Materials"
3. For each tracked product:
   - Enter quantity (or keep pre-filled)
   - Click **Lot/Serial** dropdown
   - Select lot (e.g., LOT001) or create new
4. Click "Allocate"
5. Materials allocated with full lot traceability

**Time**: ~20 seconds

---

### Scenario 4: Serial-Tracked Products

**Situation**: Allocating products tracked by serial number

**Steps**:
1. Open MO
2. Click "Allocate Materials"
3. For serial product:
   - Quantity already set to 1.0 (one serial = one unit)
   - Select serial number from dropdown
   - If allocating multiple serials, you'll need multiple lines
4. Click "Allocate"
5. Serial-tracked material allocated

**Important**: You can only allocate 1.0 unit per serial number

**Time**: ~20 seconds per serial

---

### Scenario 5: Multiple Stock Requests

**Situation**: MO is linked to multiple stock requests

**Steps**:
1. Open MO
2. Click "Allocate Materials"
3. Wizard shows materials from ALL linked stock requests
4. Each line shows which request it came from (in "Stock Request" column)
5. Review and allocate as normal
6. Materials consumed from respective requests

**Note**: The wizard automatically aggregates all available materials

**Time**: ~10-30 seconds depending on complexity

## Tips & Tricks

### Tip 1: Set to Zero to Skip
If you see materials you don't want to allocate now, just set quantity to `0` instead of deleting the line.

### Tip 2: Check the Badge
The "Allocate Materials" button may show a badge with the count of available material lines, helping you know how many items are ready.

### Tip 3: Use Notes for Context
Use the "Notes" field to add context about why you allocated that quantity or any special instructions.

### Tip 4: Allocate in Multiple Steps
You don't have to allocate everything at once. Allocate what you need now, and the rest remains available for later.

### Tip 5: Check Chatter for History
All allocations are logged in the MO's chatter with full details including who allocated, when, and how much.

## Validation & Error Messages

The system validates your input and will show errors if:

### Error: "Quantity exceeds available"
**Cause**: You're trying to allocate more than what's available
**Solution**: Reduce the quantity to the available amount or less

### Error: "Lot/Serial required"
**Cause**: Product requires tracking but no lot/serial was specified
**Solution**: Select a lot or serial number from the dropdown

### Error: "Quantity must be 1.0 for serial"
**Cause**: Serial-tracked products must have quantity of exactly 1.0
**Solution**: Change quantity to 1.0 (one serial = one unit)

### Error: "No materials available to allocate"
**Cause**: All materials have been allocated already, or none were issued
**Solution**: 
- Issue more materials via stock request, OR
- Check if materials already consumed in Components tab

### Warning: Button not visible
**Cause**: No materials are currently available to allocate
**Check**:
1. Are stock requests linked to this MO?
2. Have the pickings been validated (materials issued)?
3. Have all materials already been allocated?
4. Is the MO in a valid state (not done/cancelled)?

## Comparison with Original Allocation

You now have TWO ways to allocate materials:

### Quick Allocation (NEW)
✅ Use when: Working from the MO directly
✅ Best for: Single MO allocation
✅ Steps: 3 clicks
✅ Speed: Very fast
✅ Navigation: Stay on MO form

### Original Allocation (Still Available)
✅ Use when: Working from Stock Request view
✅ Best for: Allocating to multiple MOs
✅ Steps: 5-6 clicks
✅ Speed: Standard
✅ Navigation: From Stock Request form

**Both methods are equally valid** - choose based on your workflow!

## Keyboard Shortcuts

When in the allocation wizard:
- `Tab`: Move to next field
- `Shift+Tab`: Move to previous field
- `Enter`: Move to next line (in editable tree)
- `Esc`: Close wizard (without saving)

## Troubleshooting

### Problem: Button disappeared after opening wizard
**Cause**: Normal behavior - button visibility recalculates based on current data
**Solution**: Refresh the page if needed

### Problem: Allocated but Components tab not updating
**Cause**: Page cache
**Solution**: Refresh the browser or click to another tab and back

### Problem: Cannot allocate - MO is done
**Cause**: MO is in 'done' or 'cancelled' state
**Solution**: Cannot allocate to completed/cancelled MOs

### Problem: Lot not in dropdown
**Cause**: Lot doesn't exist for this product
**Solution**: Type the lot number to create a new one

## Best Practices

1. **Allocate as you produce**: Allocate materials just before or during production for accurate tracking

2. **Use partial allocation**: If uncertain about quantities, allocate what you're sure about first

3. **Check before allocating**: Review the available quantities match your expectations

4. **Add notes for special cases**: Use notes field to document unusual allocations

5. **Verify after allocation**: Check the Components tab to confirm consumption

6. **Keep lots consistent**: When possible, use the same lot for the same product in one MO

## Need More Help?

- **For stock request creation**: See main README.md
- **For original allocation method**: See allocation wizard documentation
- **For technical details**: See docs/ALLOCATE_MATERIALS_FEATURE.md

## Quick Reference Card

```
┌─────────────────────────────────────────────────┐
│         QUICK ALLOCATION WORKFLOW               │
├─────────────────────────────────────────────────┤
│                                                 │
│  1. Open MO                                     │
│     ↓                                           │
│  2. Click "Allocate Materials"                  │
│     ↓                                           │
│  3. Review & Adjust Quantities                  │
│     ↓                                           │
│  4. Add Lots/Serials (if needed)                │
│     ↓                                           │
│  5. Click "Allocate"                            │
│     ↓                                           │
│  ✓ Done! Materials Consumed                     │
│                                                 │
└─────────────────────────────────────────────────┘

Total Time: ~5-30 seconds depending on complexity
```

## Summary

The Quick Allocation feature makes material allocation **simple**, **fast**, and **error-free**. With just 3 clicks from the MO form, you can allocate materials without navigating multiple screens, while maintaining full traceability and validation.

**Happy allocating! 🎉**
