# Dispatch Report Full A4 Configuration

## Overview
This module has been enhanced to provide comprehensive configuration options for full A4 page coverage in dispatch reports.

## Key Features

### 1. **Full Page Coverage (A4)**
- Zero margins configuration (0mm top, bottom, left, right)
- Optimized for complete A4 page utilization (210mm x 297mm)
- Configurable DPI settings (96, 150, 200, 300 DPI)

### 2. **Comprehensive Position Configuration**

#### Header Section (ส่วนหัวเอกสาร)
- Document Number position (เลขที่เอกสาร)
- Document Date position (วันที่เอกสาร)
- Company Logo and Info (โลโก้และข้อมูลบริษัท)
- Document Title (ชื่อเอกสาร)

#### Customer Information (ข้อมูลลูกค้า)
- Customer Name (ชื่อลูกค้า)
- Customer Address with width control (ที่อยู่ลูกค้า)
- Customer Phone (เบอร์โทรศัพท์)

#### Shipping Information (ข้อมูลการจัดส่ง)
- Shipping Method (วิธีการจัดส่ง)
- Vehicle Type (ประเภทยานพาหนะ)
- Vehicle Plate (ทะเบียนรถ)
- Driver Name (ชื่อคนขับรถ)
- Dispatch Location (สถานที่จัดส่ง)

#### Product Table (ตารางรายการสินค้า)
- Configurable table position and width
- Adjustable column widths for:
  - No. (ลำดับที่)
  - Product Code (รหัสสินค้า)
  - Product Name (ชื่อสินค้า)
  - Description (รายละเอียด)
  - Quantity (จำนวน)
  - Unit (หน่วย)
  - Unit Price (ราคาต่อหน่วย)
  - Remark (หมายเหตุ)
- Configurable line height
- Max lines per page setting

#### Footer Section (ส่วนท้ายเอกสาร)
- Total Quantity position (ยอดรวมจำนวน)
- Total Amount position (ยอดรวมเงิน)
- Note section (หมายเหตุ)

#### Signature Section (ส่วนลายเซ็น)
- Sender Signature (ผู้ส่ง)
- Checker Signature (ผู้ตรวจสอบ)
- Receiver Signature (ผู้รับ)
- Approver Signature (ผู้อนุมัติ)
- Configurable signature spacing

### 3. **Typography Settings**

- **Font Sizes:**
  - Base font size (ขนาดตัวอักษรพื้นฐาน): 14px
  - Header font size (ขนาดหัวข้อ): 16px
  - Small font size (ขนาดเล็ก): 12px
  - Title font size (ขนาดชื่อเอกสาร): 20px

- **Font Family:** Sarabun, TH Sarabun New, Arial (รองรับภาษาไทย)

- **Line Spacing:** Configurable (default 1.2)

### 4. **Page Settings**

- **Paper Sizes:**
  - Letter (8.5" x 11")
  - A4 (210mm x 297mm) - Default
  - Legal (8.5" x 14")
  - A5 (148mm x 210mm)
  - Custom

- **Print Quality Modes:**
  - Screen Preview (96 DPI)
  - Draft Print (150 DPI)
  - Standard Print (200 DPI)
  - High Quality (300 DPI)

### 5. **Layout Options**

- Show/Hide sections:
  - Header Section
  - Footer Section
  - Signature Section
  - Company Logo
  
- Table settings:
  - Border width
  - Border color
  - Show/Hide borders

- Text alignment:
  - Default alignment
  - Header alignment

### 6. **Background Template**

- Upload form template image
- Adjustable opacity (0.0 - 1.0)
- Show/Hide in preview
- Helps in accurate field positioning

## Configuration Fields

### Position Fields (in pixels)
All position fields use pixel units based on the current DPI setting:
- At 96 DPI: A4 = 794px x 1123px
- At 300 DPI: A4 = 2480px x 3508px

### Helper Methods

```python
# Convert millimeters to pixels
pixels = config.get_mm_to_px(mm_value)

# Convert pixels to millimeters
mm = config.get_px_to_mm(px_value)
```

## Usage

### 1. Access Configuration
Navigate to: Inventory → Configuration → Dispatch Report Config

### 2. Create New Configuration
- Click "Create"
- Set configuration name
- Adjust positions as needed
- Set as default if required

### 3. Reset to Defaults
Use the `action_reset_to_a4_defaults()` method to reset all values to standard A4 settings.

### 4. Apply Full Page Layout
Use the `action_apply_full_page_layout()` method to optimize for maximum A4 coverage:
- Sets all margins to 0
- Maximizes table width (754px)
- Optimizes vertical spacing
- Increases max lines per page to 18

## Technical Details

### Model: `dispatch.report.config`

**Location:** `models/dispatch_report_config.py`

**Key Methods:**
- `get_default_config()` - Get default configuration
- `action_reset_to_a4_defaults()` - Reset to A4 defaults
- `action_apply_full_page_layout()` - Apply full page optimization
- `get_mm_to_px(mm_value)` - Convert mm to pixels
- `get_px_to_mm(px_value)` - Convert pixels to mm

### Report Template

**Location:** `report/dispatch_report.xml`

**Paper Format ID:** `paperformat_dispatch_report`

**Key Features:**
- Zero margins for full coverage
- A4 Portrait orientation
- 96 DPI default
- Disable shrinking enabled

## Best Practices

1. **For Full A4 Coverage:**
   - Set all margins to 0mm
   - Use table_left: 20px, table_width: 754px
   - Position elements within safe print area

2. **For Accurate Positioning:**
   - Upload background template image
   - Adjust opacity to 0.3-0.5
   - Use preview to fine-tune positions

3. **For Print Quality:**
   - Use 96 DPI for screen preview
   - Use 300 DPI for final printing
   - Test print on actual printer

4. **For Thai Language:**
   - Ensure Sarabun font is available
   - Use appropriate font sizes (14-16px)
   - Test with actual Thai text

## Troubleshooting

### Issue: Content cut off at edges
**Solution:** Reduce table_width or increase table_left value

### Issue: Text overlapping
**Solution:** Increase line_height or reduce font_size

### Issue: Empty space on page
**Solution:** Increase max_lines_per_page or reduce line_height

### Issue: Thai characters not displaying
**Solution:** Ensure Sarabun font files are in static/fonts/ directory

## Update Notes

**Version:** 17.0.1.0.0
**Last Updated:** December 2025

**Changes:**
- Added comprehensive position configuration
- Implemented full A4 page coverage
- Added DPI and print quality settings
- Enhanced typography options
- Added helper methods for unit conversion
- Improved documentation with Thai language support
