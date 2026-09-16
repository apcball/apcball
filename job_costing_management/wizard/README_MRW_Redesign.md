# Material Requisition Wizard - Redesign Documentation

## Overview
The Material Requisition Wizard has been redesigned to improve usability, especially for projects with 100+ BOQ lines. The new design focuses on making material selection FAST and EASY.

## Key Improvements

### 1. Search & Filter Functionality
- **Quick Search Box**: Search by product name, code, or description
- **BOQ Category Filter**: Filter materials by their BOQ category
- **Product Category Filter**: Filter by product's internal category
- **Cost Type Filter**: Currently defaults to 'material' (extensible for future)
- **Group By Options**: Group by BOQ Category, Product Category, or no grouping

### 2. Selection Interface
- **Checkbox/Toggle Selection**: Items are NOT auto-selected - user must explicitly select
- **Select All Button**: Selects all currently filtered items
- **Deselect All Button**: Clears all selections
- **Selection Counter**: Shows "X of Y items selected"
- **Visual Feedback**: Selected rows are highlighted in green

### 3. Display Improvements
- **Tree View with Grouping**: Grouped display by category
- **Pagination**: 100 items per page for large lists
- **Inline Editing**: Edit quantities directly in the list
- **Color Coding**:
  - 🟢 Green = Selected items
  - 🟡 Yellow = Quantity exceeds remaining BOQ
  - ⚪ Gray = Fully requisitioned items
- **Key Information Display**:
  - Product name
  - Description
  - BOQ Quantity (planned)
  - Already Requisitioned
  - Remaining Quantity
  - Requested Quantity (editable)
  - Unit of Measure
  - Estimated Cost
  - Total Cost
  - Status

### 4. Quantity Adjustment
- **Default to Remaining**: Each line defaults to the remaining quantity
- **Inline Editing**: Click and type to adjust quantities
- **Validation**: Warnings shown when quantity exceeds remaining
- **Visual Warnings**: Yellow highlighting for exceeding quantities

### 5. Preview Before Create
- **Summary View**: See all selected items before creating
- **Total Statistics**:
  - Total items selected
  - Total quantity
  - Estimated total cost
- **Requisition Details**: Review purpose, date, priority
- **Navigation**: Back to selection or Confirm to create

## User Flow

1. **Open Wizard**: From BOQ form, click "Create Material Requisition"
2. **Select Materials**:
   - Use search box to find specific items
   - Apply filters to narrow down list
   - Toggle selection for desired items
   - Adjust quantities as needed
3. **Review**: Click "Next: Review" to see summary
4. **Create**: Click "Create Requisition" to finalize

## Technical Details

### Models Updated
- `boq.material.requisition.wizard` - Main wizard model
- `boq.material.requisition.wizard.line` - Wizard line items

### New Fields Added

**BOQMaterialRequisitionWizard:**
- `wizard_state` - Controls wizard flow (selection/preview)
- `search_term` - Search functionality
- `category_filter` - BOQ category filter
- `product_category_filter` - Product category filter
- `cost_type_filter` - Cost type filter
- `group_by` - Grouping option
- `total_lines_count` - Statistics
- `selected_lines_count` - Statistics
- `selected_total_quantity` - Statistics
- `selected_total_cost` - Statistics
- `available_category_ids` - Quick category selection

**BOQMaterialRequisitionWizardLine:**
- `category_id` - BOQ category reference
- `product_category_id` - Product category reference
- `category_name` - Display name
- `product_category_name` - Display name
- `category_sequence` - For ordering
- `has_warning` - Computed warning flag

### New Methods

**BOQMaterialRequisitionWizard:**
- `action_select_all()` - Select all filtered items
- `action_deselect_all()` - Deselect all items
- `action_clear_filters()` - Reset all filters
- `action_go_to_preview()` - Navigate to preview state
- `action_go_back_to_selection()` - Return to selection state
- `_compute_filtered_lines()` - Apply filters
- `_compute_statistics()` - Calculate summary stats

**BOQMaterialRequisitionWizardLine:**
- `_compute_category_sequence()` - Category ordering
- `_onchange_requested_quantity()` - Validation with warnings

## Performance Optimizations

1. **Lazy Loading**: Tree view loads 100 items per page
2. **Computed Fields**: Statistics calculated on-demand
3. **Filtering**: Client-side search for instant results
4. **No Auto-Select**: Reduces memory usage with large datasets

## Future Enhancements

1. **Saved Filters**: Allow users to save common filter combinations
2. **Bulk Edit**: Edit quantities for multiple selected items at once
3. **Import/Export**: Export selection to Excel, import back
4. **Smart Suggestions**: AI-powered material suggestions based on project type
5. **Mobile Optimization**: Improved touch interface for tablets

## Testing Scenarios

### Scenario 1: Small Project (10-20 lines)
- Search should find items instantly
- All selection buttons work correctly
- Preview shows accurate summary

### Scenario 2: Medium Project (50-100 lines)
- Pagination works (100 items per page)
- Filters reduce list effectively
- No performance degradation

### Scenario 3: Large Project (100+ lines)
- Lazy loading prevents browser lag
- Search and filter remain responsive
- Selection state persists correctly
- Create operation completes successfully

### Scenario 4: Filter Combinations
- Search + Category filter
- Product category + BOQ category
- Clear filters resets everything
- Selections persist after filtering

### Scenario 5: Edge Cases
- BOQ with no remaining quantities (handled)
- All items exceeding BOQ quantities (warning shown)
- Mixed units of measure (handled per line)
- Empty search results (graceful handling)

## Migration Notes

No database migration required - this is a wizard (transient model). Changes are backward compatible with existing BOQ data.

## UI/UX Guidelines Followed

1. **Progressive Disclosure**: Two-step process (select then review)
2. **Visual Hierarchy**: Important info prominent, details available
3. **Immediate Feedback**: Selections and filters show instantly
4. **Error Prevention**: Warnings before errors
5. **Efficiency**: Power users can select/filter quickly
6. **Forgiveness**: Easy to go back and modify selections