# Job Costing Management for Construction

A comprehensive Odoo 17 module for construction project job costing, material management, and subcontractor coordination.

## Features

### 📋 Job Cost Sheets
- **Three-tab structure**: Materials, Labour, Overheads
- **Real-time tracking**: Planned vs actual cost comparison
- **Variance analysis**: Identify cost overruns and savings
- **Integration**: Purchase orders, timesheets, vendor bills
- **BOQ Integration**: Create cost lines from Bill of Quantities

### 📊 Bill of Quantities (BOQ)
- **Comprehensive BOQ Management**: Create detailed material lists
- **Template System**: Reusable templates for similar projects
- **Cost Calculations**: Advanced calculations with waste and contingency
- **Category Organization**: Structured item categorization
- **Material Requisition Integration**: Direct creation from BOQ lines
- **Professional Reports**: Client-ready BOQ documentation
- **Status Tracking**: Monitor procurement progress for each item

### 🏗️ Project & Contract Management
- Enhanced project views with job costing capabilities
- Contract amount and date tracking
- Project manager assignment
- Cost progress monitoring and reporting

### 📝 Job Orders/Work Orders
- Kanban-based visual management
- Material planning and consumption tracking
- Stage-based progress monitoring
- Sub-job order support for complex projects

### 🛒 Material Requisition System
- Employee material request workflow
- Multi-level approval process (Department → Manager)
- Auto-generation of purchase orders and internal transfers
- BOQ (Bill of Quantities) management and integration
- Material requisition from BOQ lines
- Vendor selection and cost estimation

### 👷 Subcontractor Management
- Specialized partner records
- Trade license and certification tracking
- Specialization and rating system
- Project assignment and performance metrics

### 📊 Advanced Reporting
- Comprehensive cost analysis reports
- Project profitability dashboard
- Material usage and waste reports
- Variance analysis for better decision making

## Installation

1. Copy the module to your Odoo addons directory
2. Update the app list in Odoo
3. Install "Job Costing Management for Construction"
4. Configure job types and stages in Configuration menu
5. Set up your first job project

## Configuration

### Initial Setup
1. **Job Types**: Define types of work (Construction, Electrical, Plumbing, etc.)
2. **Job Stages**: Set up workflow stages (Draft, Planning, In Progress, Done, etc.)
3. **Analytic Accounts**: Enable for cost tracking
4. **Employee Locations**: Set up destination locations for material requisitions

### Creating Your First Job Project
1. Go to Projects → Create new project
2. Enable "Is Job Project"
3. Select appropriate Job Type
4. Assign Project Manager
5. Set Contract details (amount, date, client)

### Setting Up Job Cost Sheets
1. From project, click "Create Job Cost Sheet"
2. Add material costs in Materials tab
3. Add labour costs in Labour tab
4. Add overhead costs in Overheads tab
5. Approve the cost sheet

## Usage Workflow

### 1. Project Planning
- Create job project
- Define job orders/work orders
- Create job cost sheet with planned costs
- Assign team members and subcontractors

### 2. Material Management
- Employees create material requisitions
- Department managers approve requests
- Requisition managers process approvals
- System generates purchase orders or internal transfers

### 3. Cost Tracking
- Purchase orders link to job cost lines
- Timesheets link to labour cost lines
- Vendor bills update actual costs
- Real-time variance calculation

### 4. Progress Monitoring
- Update job order stages
- Monitor cost progress vs planned
- Generate reports for stakeholders
- Adjust planning based on actuals

## Technical Information

### Dependencies
- `base` - Core Odoo functionality
- `project` - Project management
- `purchase` - Purchase management
- `stock` - Inventory management
- `hr_timesheet` - Timesheet tracking
- `account` - Accounting integration
- `analytic` - Analytic accounting
- `hr` - Human resources
- `mail` - Messaging and activities
- `portal` - Portal access

### Database Models
- `job.type` - Job type definitions
- `job.stage` - Job workflow stages  
- `job.cost.sheet` - Main job costing document
- `job.cost.line` - Individual cost lines
- `job.order` - Job orders/work orders
- `material.requisition` - Material request system
- `boq.boq` - Bill of Quantities main document
- `boq.line` - Individual BOQ items
- `boq.category` - BOQ item categorization
- `boq.template` - Reusable BOQ templates
- `job.note` - Project and job notes

### Security Groups
- **Job Costing User**: Create and edit own job records
- **Job Costing Manager**: Full access to all job records
- **Material Requisition User**: Create material requisitions
- **Material Requisition Manager**: Approve and manage requisitions
- **Department Manager**: Approve department requisitions

## Customization

The module is designed to be easily customizable:

- **Custom Job Types**: Add industry-specific job categories
- **Additional Cost Categories**: Extend beyond Material/Labour/Overhead
- **Custom Approval Workflows**: Modify requisition approval process
- **Custom Reports**: Add specific reporting requirements
- **Integration**: Connect with other business systems

## Support

For support, customization, or feature requests:
- Create an issue in the project repository
- Contact the development team
- Check the documentation for common solutions

## License

This module is licensed under LGPL-3. See LICENSE file for details.

## Contributors

- Development Team
- Community Contributors
- Beta Testers

---

**Version**: 17.0.1.0.0  
**Last Updated**: 2024  
**Odoo Version**: 17.0+
