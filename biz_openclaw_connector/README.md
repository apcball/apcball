# Biz OpenClaw Connector

OpenClaw AI Audit Service Integration for Odoo 17

## Overview

This module integrates Odoo with the OpenClaw AI audit service, providing AI-powered invoice auditing and suggestion capabilities.

## Features

- **Configuration Management**: Centralized API configuration with connection testing
- **Job Queue**: Asynchronous job processing with retry mechanism
- **Suggestion Management**: AI-generated suggestions with approval workflow
- **Invoice Integration**: AI Audit button for draft invoices
- **Automated Processing**: Cron job for processing pending jobs
- **Security**: Role-based access control for Accounting Managers

## Installation

1. Copy the `biz_openclaw_connector` folder to your Odoo `addons` directory
2. Update Odoo module list
3. Install the module from Apps menu

## Configuration

1. Navigate to **Accounting > Configuration > OpenClaw > Configuration**
2. Configure your OpenClow API settings:
   - **Base URL**: Your OpenClow API endpoint (e.g., https://api.openclaw.com)
   - **API Token**: Your authentication token
   - **Timeout**: Request timeout in seconds (default: 30)
3. Click **Test Connection** to verify your configuration

## Usage

### Invoice AI Audit

1. Create or open a draft invoice
2. Click the **AI Audit** button in the header
3. The invoice will be queued for AI processing
4. Once processed, suggestions will appear on the smart button
5. Review and accept/reject suggestions as needed

### Managing Jobs

Navigate to **Accounting > Configuration > OpenClaw > Jobs**:
- View job status (Pending, Processing, Done, Error)
- Retry failed jobs (up to 3 attempts)
- View payload and response details
- Access source records

### Managing Suggestions

Navigate to **Accounting > Configuration > OpenClaw > Suggestions**:
- View AI-generated suggestions
- Accept or reject suggestions
- Add notes for rejected suggestions
- Track approval history

## API Specification

### Endpoint
```
POST {base_url}/api/jobs
```

### Headers
```
Authorization: Bearer {api_token}
Content-Type: application/json
```

### Request Payload (Invoice Audit)
```json
{
  "event_type": "invoice_audit",
  "model_name": "account.move",
  "record_id": 123,
  "data": {
    "invoice_type": "out_invoice",
    "invoice_number": "INV/2024/001",
    "invoice_date": "2024-01-01",
    "partner": {
      "id": 1,
      "name": "Customer Name",
      "vat": "1234567890",
      "email": "customer@example.com"
    },
    "journal": "Customer Invoices",
    "amount_untaxed": 1000.00,
    "amount_tax": 70.00,
    "amount_total": 1070.00,
    "currency": "USD",
    "state": "draft",
    "lines": [...]
  }
}
```

### Response Format
```json
{
  "status": "success",
  "suggestions": [
    {
      "type": "risk_alert",
      "risk_score": 0.75,
      "confidence": 85.0,
      "summary": "Potential duplicate invoice detected",
      "details": {...}
    }
  ]
}
```

## Security

- **OpenClaw Manager**: Full access to configuration and all records
- **OpenClaw User**: Can create suggestions and view jobs/config
- **Accounting Manager**: Inherited full access

## Technical Details

### Models

- `openclaw.config`: API configuration
- `openclaw.job`: Job queue
- `openclaw.suggestion`: AI suggestions
- `openclaw.client`: Abstract API client

### Dependencies

- `base`: Odoo base module
- `account`: Odoo accounting module

### External Libraries

- `requests`: HTTP client for API calls

## Cron Job

- **Name**: Process OpenClaw Jobs
- **Interval**: Every 5 minutes
- **Method**: `openclaw.job.process_pending_jobs()`

## Troubleshooting

### Connection Failed
- Verify Base URL is correct and accessible
- Check API token validity
- Test network connectivity from Odoo server

### Jobs Not Processing
- Check cron job is active
- Verify configuration is active
- Review error messages in job records

### No Suggestions Generated
- Verify API response format
- Check job completion status
- Review response_json field in job record

## License

LGPL-3

## Support

For issues and questions, please contact your Odoo support provider.
