# Validation Fix - Allow Auto-Detect Without Selecting Products

## Issue
ผู้ใช้ต้องเลือก products ก่อนเสมอ แม้ว่าจะเปิดใช้ auto-detect แล้วก็ตาม
Error: "Validation Error: Please select at least one product."

## Solution
แก้ไข validation logic ให้ยอมรับได้เมื่อ:
- ไม่มีสินค้าถูกเลือก
- แต่เปิดใช้ "Auto-detect Products" 
- มีการเลือก location(s)

## Changes Made

### 1. Updated `_get_products_to_process()` Method

**Before:**
```python
if self.mode == 'product':
    if not self.product_ids:
        raise ValidationError("Please select at least one product.")
```

**After:**
```python
if self.mode == 'product':
    if not self.product_ids:
        # Allow empty products if auto-detect is enabled
        if not self.auto_detect_products:
            raise ValidationError("Please select at least one product, or enable 'Auto-detect Products'.")
        # Return empty recordset, will be populated by auto-detect
        return self.env['product.product']
```

### 2. Added Notification When No Issues Found

```python
if self.auto_detect_products and self.location_ids:
    detected_products = self._auto_detect_products_with_issues()
    if detected_products:
        self.product_ids = [(6, 0, detected_products.ids)]
    else:
        # Show success notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'No Issues Found',
                'message': 'No products with valuation issues found in selected locations.',
                'type': 'success',
            }
        }
```

### 3. Enhanced Result Message

```python
# Add auto-detect info to message if used
if self.auto_detect_products and self.location_ids:
    message += f"\n\nAuto-detected {len(products)} product(s) with valuation issues in selected locations."
```

## New User Flow

### ขั้นตอนที่ถูกต้อง (ไม่ต้องเลือกสินค้า):

1. เปิด wizard
2. เลือก Company
3. เลือก Mode = "Products" (ไม่ต้องเลือกสินค้า)
4. เลือก Location(s)
5. ✅ เปิด "Auto-detect Products"
6. ❌ ปิด "Check Missing Account Moves" (สำหรับ manual valuation)
7. กำหนด Date Range (optional)
8. **กด "Compute Plan" โดยตรง** (ไม่ต้องเลือกสินค้า)
9. ระบบจะหาสินค้าที่มีปัญหาและเติมให้อัตโนมัติ

## Error Messages

### เมื่อไม่เลือกสินค้า และไม่เปิด auto-detect:
```
Validation Error
Please select at least one product, or enable 'Auto-detect Products'.
```

### เมื่อเปิด auto-detect แต่ไม่พบสินค้าที่มีปัญหา:
```
✓ No Issues Found
No products with valuation issues found in selected locations.
```

### เมื่อพบสินค้าที่มีปัญหา:
```
✓ Plan Computed
Found 25 SVL(s) and 15 Journal Entry(ies) for 5 product(s).

Auto-detected 5 product(s) with valuation issues in selected locations.
```

## Benefits

1. ✅ **ง่ายต่อการใช้งาน**: ไม่ต้องเลือกสินค้าเอง
2. ✅ **รวดเร็ว**: กด Compute Plan ได้ทันที
3. ✅ **แม่นยำ**: ระบบหาสินค้าที่มีปัญหาเอง
4. ✅ **ข้อความชัดเจน**: แจ้งเตือนทุกกรณี
5. ✅ **Backward Compatible**: ยังเลือกสินค้าเองได้ตามเดิม

## Testing

### Test Case 1: Auto-detect with issues found
```
Input:
- Mode: Products (empty)
- Locations: WH/Stock
- Auto-detect: ✅
- Check Account Moves: ❌

Expected:
- ✅ Finds products with issues
- ✅ Populates Products field
- ✅ Shows detailed plan
- ✅ Shows notification with count
```

### Test Case 2: Auto-detect with NO issues found
```
Input:
- Mode: Products (empty)
- Locations: WH/Stock
- Auto-detect: ✅
- Check Account Moves: ❌

Expected:
- ✅ Shows "No Issues Found" notification
- ✅ No products selected
- ✅ No error
```

### Test Case 3: No auto-detect, no products
```
Input:
- Mode: Products (empty)
- Auto-detect: ❌

Expected:
- ❌ Validation Error
- Message: "Please select at least one product, or enable 'Auto-detect Products'."
```

### Test Case 4: Manual product selection (traditional way)
```
Input:
- Mode: Products
- Products: [Product A, Product B]
- Auto-detect: ❌

Expected:
- ✅ Works as before
- ✅ No changes to existing flow
```

## Notes

- Validation ถูกข้ามเฉพาะเมื่อ `auto_detect_products == True`
- ถ้าไม่เปิด auto-detect ยังคงต้องเลือกสินค้าตามเดิม
- Empty product list + auto-detect = OK
- Empty product list + no auto-detect = Error
