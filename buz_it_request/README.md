# IT Request Suite Module (buz_it_request)

## Overview
This module provides a complete IT request management solution for Odoo 17, featuring three main components:
1. IT Ticket Issue - For reporting and tracking IT problems
2. IT Access Request - For requesting system access
3. IT Procurement Request - For requesting IT equipment procurement

## Features

### IT Ticket Issue (it.ticket.issue)
- Ticket creation with automatic numbering
- Categorization and prioritization
- SLA tracking based on priority
- Assignment to IT technicians
- Resolution tracking with cause and notes
- State workflow: draft → triage → in_progress → waiting_user → done → cancel

### IT Access Request (it.request.access)
- Request for system access (email, ERP, VPN, etc.)
- Multi-level approval workflow
- Checklist implementation
- State workflow: draft → to_manager_approve → manager_approved → to_it → it_in_progress → done

### IT Procurement Request (it.request.procurement)
- Request for IT equipment and supplies
- Detailed line items with products
- Integration with purchase requests or RFQs
- State workflow: draft → to_manager_approve → manager_approved → to_it → it_reviewed → pr_created → done

## Security
- IT User: Full access to all requests
- IT Manager: Full access plus configuration
- IT Requester: Can create and view own requests
- IT Manager Approver: Can approve requests for their department

## Configuration
The module includes:
- Automatic sequence generation for all request types
- Mail activities for SLA and approval reminders
- SLA policies based on priority levels
- IT categories for issue classification

## Reports
- IT Issue Report
- IT Access Request Report
- IT Procurement Request Report

## Dashboard
The module provides a dashboard view with:
- Summary of open tickets by priority
- Requests awaiting approval
- SLA status tracking
- Procurement status