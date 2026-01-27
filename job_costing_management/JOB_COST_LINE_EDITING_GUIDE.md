# Job Cost Line Editing Guide

## Overview

The Job Costing Management module now includes comprehensive job cost line editing functionality that allows users to create, edit, and manage individual cost lines with proper cost type validation and bulk editing capabilities.

## Features Implemented

### 1. Individual Job Cost Line Editing

#### Form View for Job Cost Lines
- **Dedicated form view** for editing individual job cost lines
- **Cost type selection** with radio buttons (Material, Labour, Overhead)
- **Product domain filtering** based on cost type:
  - Material: Only storable/consumable products
  - Labour: Only service products
  - Overhead: All product types
- **Automatic UOM suggestions** based on cost type
- **Real-time cost calculations** and variance analysis
- **Related records tabs** showing:
  - Purchase Orders (for Material/Overhead)
  - Timesheets (for Labour)
  - Invoice Lines (for all types)

#### Navigation and Access
- **Menu item**: Job Costing → Job Costs → Job Cost Lines
- **Smart button** on Job Cost Sheet showing total cost lines count
- **Edit buttons** in each cost tab of Job Cost Sheet
- **Direct form access** from tree views

### 2. Cost Type Change Validation

#### Automatic Validations
- **Product compatibility check**: Ensures selected products match cost type
- **Automatic product clearing** when cost type changes
- **UOM suggestions**: 
  - Labour → Hours
  - Material → Units
  - Overhead → Appropriate UOM

#### Error Prevention
- **Constraint validation** prevents incompatible product-cost type combinations
- **Clear error messages** guide users to correct selections
- **Onchange methods** provide immediate feedback

### 3. Bulk Editing Capabilities

#### Cost Type Update Wizard
- **Bulk cost type changes** for multiple selected lines
- **Product clearing option** to ensure compatibility
- **Automatic UOM adjustment** based on new cost type

#### Bulk Edit Wizard
- **Multiple field updates** in one operation:
  - Cost Type
  - Unit Cost
  - Planned Quantity
  - Analytic Account
- **Selective updates** - choose which fields to modify
- **Batch processing** for efficiency

### 4. Enhanced User Interface

#### Tree View Improvements
- **Color coding** by cost type:
  - Material: Blue
  - Labour: Green
  - Overhead: Orange
- **Multi-edit support** for quick inline changes
- **Action buttons** in header for bulk operations
- **Sortable columns** with handle for sequence management

#### Form View Features
- **Tabbed interface** showing related records
- **Real-time calculations** for totals and variances
- **Update buttons** for refreshing actual costs
- **Mail tracking** for change history

### 5. Security and Permissions

#### Access Control
- **User level**: Read, Write, Create (no delete)
- **Manager level**: Full access including delete
- **Proper security groups** integration
- **Record-level security** through cost sheet access

## Usage Instructions

### Editing Individual Cost Lines

1. **From Job Cost Sheet**:
   - Open any Job Cost Sheet
   - Click the "Cost Lines" smart button, or
   - Use the edit button (pencil icon) in any cost tab

2. **From Menu**:
   - Navigate to Job Costing → Job Costs → Job Cost Lines
   - Select any line to edit

3. **Changing Cost Type**:
   - Open the cost line form
   - Select new cost type using radio buttons
   - Product will be cleared automatically if incompatible
   - Select appropriate product for new cost type
   - Save changes

### Bulk Operations

1. **Bulk Cost Type Update**:
   - Select multiple cost lines in tree view
   - Click "Update Cost Type" button
   - Choose new cost type
   - Optionally clear product selections
   - Confirm update

2. **Bulk Field Updates**:
   - Select multiple cost lines in tree view
   - Click "Bulk Edit" button
   - Check fields to update
   - Enter new values
   - Confirm update

### Best Practices

1. **Cost Type Changes**:
   - Always verify product compatibility after cost type changes
   - Review UOM settings for accuracy
   - Update planned quantities if needed

2. **Product Selection**:
   - Use appropriate product types for each cost type
   - Ensure products have correct UOM configured
   - Set realistic standard prices for automatic cost calculation

3. **Bulk Operations**:
   - Use filters to select relevant cost lines
   - Test with small batches first
   - Review changes before confirming

## Technical Implementation

### Models Enhanced
- `job.cost.line`: Added mail tracking, validation, and editing methods
- `job.cost.sheet`: Added navigation methods and smart buttons

### New Wizards
- `job.cost.line.wizard`: Cost type update wizard
- `job.cost.line.bulk.edit.wizard`: Bulk editing wizard

### Views Added
- Job Cost Line form view with tabbed interface
- Job Cost Line tree view with bulk actions
- Job Cost Line search view with filters
- Wizard views for bulk operations

### Security
- Proper access rights for job cost lines
- Integration with existing security groups
- Record-level access control

## Troubleshooting

### Common Issues

1. **Product not compatible with cost type**:
   - Solution: Clear product selection and choose compatible product

2. **Cannot change cost type**:
   - Check user permissions
   - Ensure cost line is not locked by related records

3. **Bulk operations not working**:
   - Verify multiple lines are selected
   - Check user has write permissions
   - Ensure all selected lines are editable

### Error Messages

- "Material cost lines cannot use service products": Select storable/consumable product
- "Labour cost lines must use service products": Select service product
- "Please select at least one job cost line": Select lines before bulk operations

## Future Enhancements

Potential improvements for future versions:
- Cost line templates for quick creation
- Advanced filtering and grouping options
- Integration with project budgets
- Automated cost type suggestions based on product
- Approval workflows for cost changes
- Cost line copying between projects