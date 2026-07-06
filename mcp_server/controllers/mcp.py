# -*- coding: utf-8 -*-

import json
from odoo import http
from odoo import fields as odoo_fields
from odoo.http import request
from odoo.exceptions import AccessDenied
from odoo.tools.translate import _


class MCPController(http.Controller):
    """MCP Server Controller - Exposes Odoo models as MCP tools"""

    # Tool → minimum policy required
    TOOL_POLICY_MAP = {
        'sale_order_search': 'read',
        'sale_order_read': 'read',
        'sale_order_create': 'write',
        'sale_order_write': 'write',
        'sale_order_confirm': 'write',
        'sale_order_create_invoice': 'write',
        'invoice_confirm': 'write',
        'product_search': 'read',
        'product_read': 'read',
        'product_create': 'write',
        'product_write': 'write',
        'partner_search': 'read',
        'partner_read': 'read',
        'partner_create': 'write',
        'partner_write': 'write',
        'company_list': 'read',
        'company_search': 'read',
        'sale_report': 'read',
        'accounting_audit': 'read',
        'gl_report': 'read',
        'gl_variance': 'read',
        'account_move_search': 'read',
        'purchase_order_search': 'read',
        'purchase_order_read': 'read',
        'budget_report': 'read',
        'refresh_budget_mv': 'read',
        'stock_move_search': 'read',
        'stock_valuation_layer_search': 'read',
        'stock_valuation_layer_read': 'read',
    }

    POLICY_LEVELS = {'read': 0, 'write': 1}

    def _verify_api_key(self):
        """Verify API key from request headers and return key_record"""
        api_key = request.httprequest.headers.get('X-API-Key')
        if not api_key:
            raise AccessDenied(_('API Key is required'))

        key_record = request.env['mcp.api.key'].sudo().search([
            ('key', '=', api_key),
            ('active', '=', True)
        ], limit=1)

        if not key_record:
            raise AccessDenied(_('Invalid API Key'))

        # Update usage tracking
        key_record.write({
            'last_used': odoo_fields.Datetime.now(),
            'usage_count': key_record.usage_count + 1
        })

        # Set allowed company context — allow all companies the user has access to
        # so operations on records from any company work correctly
        user = key_record.user_id
        allowed_company = key_record.company_id
        if allowed_company:
            user_companies = user.company_ids.ids if user.company_ids else [allowed_company.id]
            request.update_context(
                allowed_company_ids=user_companies,
            )

        return key_record

    def _check_policy(self, key_record, tool_name):
        """Check if the API key's policy allows calling this tool"""
        required_policy = self.TOOL_POLICY_MAP.get(tool_name, 'read')
        key_policy = key_record.policy or 'read'
        if self.POLICY_LEVELS.get(key_policy, 0) < self.POLICY_LEVELS.get(required_policy, 0):
            raise AccessDenied(
                _('Policy "%(key_policy)s" does not allow calling "%(tool)s" (requires "%(required)s")',
                  key_policy=key_policy, tool=tool_name, required=required_policy)
            )

    @staticmethod
    def _mcp_tool(tool_name):
        """Decorator: verify API key, check policy, parse JSON body, handle errors."""
        import functools

        def decorator(func):
            @functools.wraps(func)
            def wrapper(self, **kwargs):
                try:
                    key_record = self._verify_api_key()
                    self._check_policy(key_record, tool_name)
                    data = json.loads(request.httprequest.data) if request.httprequest.data else {}
                    return func(self, key_record, data, **kwargs)
                except AccessDenied as e:
                    return request.make_json_response(
                        {'success': False, 'error': str(e)}, status=401)
                except Exception as e:
                    return request.make_json_response(
                        {'success': False, 'error': str(e)}, status=400)
            return wrapper
        return decorator

    @http.route('/mcp/tools', type='http', auth='public', methods=['GET'], csrf=False)
    def mcp_tools(self, **kwargs):
        """Return available MCP tools filtered by API key policy"""
        key_record = self._verify_api_key()
        key_policy = key_record.policy or 'read'
        policy_level = self.POLICY_LEVELS.get(key_policy, 0)

        tools = [
            {
                'name': 'sale_order_search',
                'description': 'Search for sale orders with optional filters',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'domain': {
                            'type': 'array',
                            'description': 'Odoo domain filter',
                            'items': {'type': 'array'}
                        },
                        'fields': {
                            'type': 'array',
                            'description': 'Fields to return',
                            'items': {'type': 'string'}
                        },
                        'limit': {
                            'type': 'integer',
                            'description': 'Maximum number of records'
                        }
                    }
                }
            },
            {
                'name': 'sale_order_read',
                'description': 'Read a specific sale order',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'id': {
                            'type': 'integer',
                            'description': 'Sale order ID'
                        },
                        'fields': {
                            'type': 'array',
                            'description': 'Fields to return',
                            'items': {'type': 'string'}
                        }
                    },
                    'required': ['id']
                }
            },
            {
                'name': 'sale_order_create',
                'description': 'Create a new sale order',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'values': {
                            'type': 'object',
                            'description': 'Field values for the sale order'
                        }
                    },
                    'required': ['values']
                }
            },
            {
                'name': 'sale_order_write',
                'description': 'Update an existing sale order',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'id': {
                            'type': 'integer',
                            'description': 'Sale order ID'
                        },
                        'values': {
                            'type': 'object',
                            'description': 'Field values to update'
                        }
                    },
                    'required': ['id', 'values']
                }
            },
            {
                'name': 'sale_order_confirm',
                'description': 'Confirm a sale order to move it from draft to sale state (triggers business logic)',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'id': {
                            'type': 'integer',
                            'description': 'Sale order ID'
                        }
                    },
                    'required': ['id']
                }
            },
            {
                'name': 'sale_order_create_invoice',
                'description': 'Create invoice from a confirmed sale order',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'id': {
                            'type': 'integer',
                            'description': 'Sale order ID (must be confirmed)'
                        }
                    },
                    'required': ['id']
                }
            },
            {
                'name': 'invoice_confirm',
                'description': 'Post/confirm an invoice (action_post) to post it to accounting',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'id': {
                            'type': 'integer',
                            'description': 'Invoice (account.move) ID'
                        }
                    },
                    'required': ['id']
                }
            },
            {
                'name': 'product_search',
                'description': 'Search for products with optional filters',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'domain': {
                            'type': 'array',
                            'description': 'Odoo domain filter',
                            'items': {'type': 'array'}
                        },
                        'fields': {
                            'type': 'array',
                            'description': 'Fields to return',
                            'items': {'type': 'string'}
                        },
                        'limit': {
                            'type': 'integer',
                            'description': 'Maximum number of records'
                        }
                    }
                }
            },
            {
                'name': 'product_read',
                'description': 'Read a specific product',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'id': {
                            'type': 'integer',
                            'description': 'Product ID'
                        },
                        'fields': {
                            'type': 'array',
                            'description': 'Fields to return',
                            'items': {'type': 'string'}
                        }
                    },
                    'required': ['id']
                }
            },
            {
                'name': 'product_create',
                'description': 'Create a new product',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'values': {
                            'type': 'object',
                            'description': 'Field values for the product'
                        }
                    },
                    'required': ['values']
                }
            },
            {
                'name': 'product_write',
                'description': 'Update an existing product',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'id': {
                            'type': 'integer',
                            'description': 'Product ID'
                        },
                        'values': {
                            'type': 'object',
                            'description': 'Field values to update'
                        }
                    },
                    'required': ['id', 'values']
                }
            },
            {
                'name': 'partner_search',
                'description': 'Search for partners (contacts/customers) with optional filters',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'domain': {
                            'type': 'array',
                            'description': 'Odoo domain filter e.g. [["name","ilike","John"]]',
                            'items': {'type': 'array'}
                        },
                        'fields': {
                            'type': 'array',
                            'description': 'Fields to return',
                            'items': {'type': 'string'}
                        },
                        'limit': {
                            'type': 'integer',
                            'description': 'Maximum number of records'
                        }
                    }
                }
            },
            {
                'name': 'partner_read',
                'description': 'Read a specific partner by ID',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'id': {
                            'type': 'integer',
                            'description': 'Partner ID'
                        },
                        'fields': {
                            'type': 'array',
                            'description': 'Fields to return',
                            'items': {'type': 'string'}
                        }
                    },
                    'required': ['id']
                }
            },
            {
                'name': 'partner_create',
                'description': 'Create a new partner (contact/customer)',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'values': {
                            'type': 'object',
                            'description': 'Field values. Must include name. Optional: phone, email, mobile, company_id, is_company, vat, street, city'
                        }
                    },
                    'required': ['values']
                }
            },
            {
                'name': 'company_list',
                'description': 'List all active companies in the system',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'fields': {
                            'type': 'array',
                            'description': 'Fields to return',
                            'items': {'type': 'string'}
                        }
                    }
                }
            },
            {
                'name': 'company_search',
                'description': 'Search for companies with optional filters',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'domain': {
                            'type': 'array',
                            'description': 'Odoo domain filter e.g. [["name","ilike","Company"]]',
                            'items': {'type': 'array'}
                        },
                        'fields': {
                            'type': 'array',
                            'description': 'Fields to return',
                            'items': {'type': 'string'}
                        },
                        'limit': {
                            'type': 'integer',
                            'description': 'Maximum number of records'
                        }
                    }
                }
            },
            {
                'name': 'sale_report',
                'description': 'Generate sales report aggregated by salesperson, team, and time period (week/month)',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'date_from': {
                            'type': 'string',
                            'description': 'Start date ISO format e.g. "2025-01-01"'
                        },
                        'date_to': {
                            'type': 'string',
                            'description': 'End date ISO format e.g. "2025-12-31"'
                        },
                        'group_by': {
                            'type': 'string',
                            'description': 'Comma-separated group keys: "salesperson", "team", "week", "month", "product". Default: "month,salesperson"'
                        },
                        'states': {
                            'type': 'array',
                            'description': 'Sale order states to include. Default: ["sale","done"]',
                            'items': {'type': 'string'}
                        },
                        'limit': {
                            'type': 'integer',
                            'description': 'Max rows (default 500)'
                        }
                    }
                }
            },
            {
                'name': 'accounting_audit',
                'description': 'Audit accounting entries for errors: unbalanced moves, date mismatches between move and move lines, stale draft entries, and suspicious amounts',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'date_from': {
                            'type': 'string',
                            'description': 'Start date filter ISO format e.g. "2025-01-01"'
                        },
                        'date_to': {
                            'type': 'string',
                            'description': 'End date filter ISO format e.g. "2025-12-31"'
                        },
                        'checks': {
                            'type': 'array',
                            'description': 'Which checks to run: "unbalanced", "date_mismatch", "stale_draft", "suspicious_amount". Default: all checks.',
                            'items': {'type': 'string'}
                        },
                        'limit': {
                            'type': 'integer',
                            'description': 'Max issues per check (default 100)'
                        }
                    }
                }
            },
            {
                'name': 'gl_report',
                'description': 'General Ledger report with opening balance, movements, and closing balance per account. Supports grouping by account, partner, journal.',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'date_from': {
                            'type': 'string',
                            'description': 'Start date ISO format e.g. "2025-01-01"'
                        },
                        'date_to': {
                            'type': 'string',
                            'description': 'End date ISO format e.g. "2025-12-31"'
                        },
                        'account_codes': {
                            'type': 'array',
                            'description': 'Filter by account codes e.g. ["1100","1200"]. Default: all accounts.',
                            'items': {'type': 'string'}
                        },
                        'group_by': {
                            'type': 'string',
                            'description': 'Group by: "account", "account_partner", "account_journal". Default: "account"'
                        },
                        'limit': {
                            'type': 'integer',
                            'description': 'Max rows (default 500)'
                        }
                    }
                }
            },
            {
                'name': 'gl_variance',
                'description': 'Compare GL balances between two periods or against expected values. Detects unexpected variances in account balances.',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'period1_from': {
                            'type': 'string',
                            'description': 'Period 1 start date e.g. "2025-01-01"'
                        },
                        'period1_to': {
                            'type': 'string',
                            'description': 'Period 1 end date e.g. "2025-03-31"'
                        },
                        'period2_from': {
                            'type': 'string',
                            'description': 'Period 2 start date e.g. "2025-04-01"'
                        },
                        'period2_to': {
                            'type': 'string',
                            'description': 'Period 2 end date e.g. "2025-06-30"'
                        },
                        'variance_threshold': {
                            'type': 'number',
                            'description': 'Minimum absolute variance to report. Default: 0.01'
                        },
                        'account_codes': {
                            'type': 'array',
                            'description': 'Filter by account codes. Default: all.',
                            'items': {'type': 'string'}
                        }
                    }
                }
            },
            {
                'name': 'account_move_search',
                'description': 'Search and read journal entries (account.move) with line details',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'domain': {
                            'type': 'array',
                            'description': 'Odoo domain filter e.g. [["journal_id.type","=","sale"]]',
                            'items': {'type': 'array'}
                        },
                        'fields': {
                            'type': 'array',
                            'description': 'Fields to return',
                            'items': {'type': 'string'}
                        },
                        'with_lines': {
                            'type': 'boolean',
                            'description': 'Include move lines detail (default false)'
                        },
                        'limit': {
                            'type': 'integer',
                            'description': 'Max records (default 80)'
                        }
                    }
                }
            },
            {
                'name': 'budget_report',
                'description': 'Search budget report by department, plan, or period',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'department_id': {
                            'type': 'integer',
                            'description': 'Filter by department ID'
                        },
                        'plan_id': {
                            'type': 'integer',
                            'description': 'Filter by budget plan ID'
                        },
                        'analytic_account_id': {
                            'type': 'integer',
                            'description': 'Filter by analytic account ID'
                        },
                        'year': {
                            'type': 'string',
                            'description': 'Filter by year e.g. "2026"'
                        },
                        'month': {
                            'type': 'string',
                            'description': 'Filter by month number e.g. "06"'
                        },
                        'limit': {
                            'type': 'integer',
                            'description': 'Max records (default 80)'
                        }
                    }
                }
            },
            {
                'name': 'refresh_budget_mv',
                'description': 'Recreate and refresh the budget report materialized view',
                'inputSchema': {
                    'type': 'object',
                    'properties': {}
                }
            },
        ]

        # Filter tools based on API key policy
        allowed_tools = []
        for tool in tools:
            tool_name = tool['name']
            required_policy = self.TOOL_POLICY_MAP.get(tool_name, 'read')
            required_level = self.POLICY_LEVELS.get(required_policy, 0)
            if policy_level >= required_level:
                allowed_tools.append(tool)

        return request.make_json_response(allowed_tools)

    @http.route('/mcp/call/sale_order_search', type='http', auth='public', methods=['POST'], csrf=False)
    def sale_order_search(self, **kwargs):
        """Search for sale orders"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'sale_order_search')
            data = json.loads(request.httprequest.data)
            domain = data.get('domain', [])
            field_list = data.get('fields', ['name', 'partner_id', 'state', 'amount_total', 'date_order'])
            limit = data.get('limit', 80)

            orders = request.env['sale.order'].sudo().search(domain, limit=limit)
            result = orders.read(field_list)

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/sale_order_read', type='http', auth='public', methods=['POST'], csrf=False)
    def sale_order_read(self, **kwargs):
        """Read a specific sale order"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'sale_order_read')
            data = json.loads(request.httprequest.data)
            order_id = data.get('id')
            field_list = data.get('fields', ['name', 'partner_id', 'state', 'amount_total', 'date_order', 'order_line'])

            if not order_id:
                return request.make_json_response({
                    'success': False,
                    'error': 'id is required'
                }, status=400)

            order = request.env['sale.order'].sudo().browse(order_id)
            if not order.exists():
                return request.make_json_response({
                    'success': False,
                    'error': 'Sale order not found'
                }, status=404)

            result = order.read(field_list)[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/sale_order_create', type='http', auth='public', methods=['POST'], csrf=False)
    def sale_order_create(self, **kwargs):
        """Create a new sale order"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'sale_order_create')
            data = json.loads(request.httprequest.data)
            values = data.get('values')

            if not values:
                return request.make_json_response({
                    'success': False,
                    'error': 'values is required'
                }, status=400)

            order = request.env['sale.order'].sudo().create(values)
            result = order.read(['name', 'partner_id', 'state', 'amount_total', 'date_order'])[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/sale_order_write', type='http', auth='public', methods=['POST'], csrf=False)
    def sale_order_write(self, **kwargs):
        """Update an existing sale order"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'sale_order_write')
            data = json.loads(request.httprequest.data)
            order_id = data.get('id')
            values = data.get('values')

            if not order_id or not values:
                return request.make_json_response({
                    'success': False,
                    'error': 'id and values are required'
                }, status=400)

            order = request.env['sale.order'].sudo().browse(order_id)
            if not order.exists():
                return request.make_json_response({
                    'success': False,
                    'error': 'Sale order not found'
                }, status=404)

            order.write(values)
            result = order.read(['name', 'partner_id', 'state', 'amount_total', 'date_order'])[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    # ─── Sale Order action endpoints ─────────────────────────────

    @http.route('/mcp/call/sale_order_confirm', type='http', auth='public', methods=['POST'], csrf=False)
    def sale_order_confirm(self, **kwargs):
        """Confirm a sale order (action_confirm)"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'sale_order_confirm')
            data = json.loads(request.httprequest.data)
            order_id = data.get('id')

            if not order_id:
                return request.make_json_response({
                    'success': False,
                    'error': 'id is required'
                }, status=400)

            order = request.env['sale.order'].sudo().browse(order_id)
            if not order.exists():
                return request.make_json_response({
                    'success': False,
                    'error': 'Sale order not found'
                }, status=404)

            order.action_confirm()
            result = order.read(['name', 'partner_id', 'state', 'amount_total', 'date_order', 'invoice_status'])[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/sale_order_create_invoice', type='http', auth='public', methods=['POST'], csrf=False)
    def sale_order_create_invoice(self, **kwargs):
        """Create invoice from a confirmed sale order (_create_invoices)"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'sale_order_create_invoice')
            data = json.loads(request.httprequest.data)
            order_id = data.get('id')

            if not order_id:
                return request.make_json_response({
                    'success': False,
                    'error': 'id is required'
                }, status=400)

            order = request.env['sale.order'].sudo().browse(order_id)
            if not order.exists():
                return request.make_json_response({
                    'success': False,
                    'error': 'Sale order not found'
                }, status=404)

            # Force company context and ensure invoice date is set
            order = order.with_company(order.company_id.id)
            invoice = order._create_invoices(
                final=data.get('final', True),
                date=data.get('date') or order.date_order.date(),
            )
            result = invoice.read(['name', 'partner_id', 'move_type', 'state', 'amount_total', 'amount_untaxed', 'invoice_date', 'invoice_date_due', 'invoice_origin'])[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/invoice_confirm', type='http', auth='public', methods=['POST'], csrf=False)
    def invoice_confirm(self, **kwargs):
        """Post/confirm an invoice (action_post)"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'invoice_confirm')
            data = json.loads(request.httprequest.data)
            invoice_id = data.get('id')

            if not invoice_id:
                return request.make_json_response({
                    'success': False,
                    'error': 'id is required'
                }, status=400)

            invoice = request.env['account.move'].sudo().browse(invoice_id)
            if not invoice.exists():
                return request.make_json_response({
                    'success': False,
                    'error': 'Invoice not found'
                }, status=404)

            invoice.action_post()
            result = invoice.read(['name', 'partner_id', 'move_type', 'state', 'amount_total', 'invoice_date', 'invoice_origin'])[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/product_search', type='http', auth='public', methods=['POST'], csrf=False)
    def product_search(self, **kwargs):
        """Search for products"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'product_search')
            data = json.loads(request.httprequest.data)
            domain = data.get('domain', [])
            field_list = data.get('fields', ['name', 'default_code', 'list_price', 'qty_available', 'type'])
            limit = data.get('limit', 80)

            products = request.env['product.product'].sudo().search(domain, limit=limit)
            result = products.read(field_list)

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/product_read', type='http', auth='public', methods=['POST'], csrf=False)
    def product_read(self, **kwargs):
        """Read a specific product"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'product_read')
            data = json.loads(request.httprequest.data)
            product_id = data.get('id')
            field_list = data.get('fields', ['name', 'default_code', 'list_price', 'qty_available', 'type', 'description_sale'])

            if not product_id:
                return request.make_json_response({
                    'success': False,
                    'error': 'id is required'
                }, status=400)

            product = request.env['product.product'].sudo().browse(product_id)
            if not product.exists():
                return request.make_json_response({
                    'success': False,
                    'error': 'Product not found'
                }, status=404)

            result = product.read(field_list)[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/product_create', type='http', auth='public', methods=['POST'], csrf=False)
    def product_create(self, **kwargs):
        """Create a new product"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'product_create')
            data = json.loads(request.httprequest.data)
            values = data.get('values')

            if not values:
                return request.make_json_response({
                    'success': False,
                    'error': 'values is required'
                }, status=400)

            product = request.env['product.product'].sudo().create(values)
            result = product.read(['name', 'default_code', 'list_price', 'type'])[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/product_write', type='http', auth='public', methods=['POST'], csrf=False)
    def product_write(self, **kwargs):
        """Update an existing product"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'product_write')
            data = json.loads(request.httprequest.data)
            product_id = data.get('id')
            values = data.get('values')

            if not product_id or not values:
                return request.make_json_response({
                    'success': False,
                    'error': 'id and values are required'
                }, status=400)

            product = request.env['product.product'].sudo().browse(product_id)
            if not product.exists():
                return request.make_json_response({
                    'success': False,
                    'error': 'Product not found'
                }, status=404)

            product.write(values)
            result = product.read(['name', 'default_code', 'list_price', 'type'])[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    # ─── Partner endpoints ──────────────────────────────────────

    @http.route('/mcp/call/partner_search', type='http', auth='public', methods=['POST'], csrf=False)
    def partner_search(self, **kwargs):
        """Search for partners (contacts/customers)"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'partner_search')
            data = json.loads(request.httprequest.data)
            domain = data.get('domain', [])
            field_list = data.get('fields', ['name', 'email', 'phone', 'mobile', 'company_id', 'is_company', 'parent_id', 'vat'])
            limit = data.get('limit', 80)

            partners = request.env['res.partner'].sudo().search(domain, limit=limit)
            result = partners.read(field_list)

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/partner_read', type='http', auth='public', methods=['POST'], csrf=False)
    def partner_read(self, **kwargs):
        """Read a specific partner by ID"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'partner_read')
            data = json.loads(request.httprequest.data)
            partner_id = data.get('id')
            field_list = data.get('fields', ['name', 'email', 'phone', 'mobile', 'company_id', 'is_company', 'parent_id', 'vat', 'street', 'city', 'zip', 'country_id', 'state_id'])

            if not partner_id:
                return request.make_json_response({
                    'success': False,
                    'error': 'id is required'
                }, status=400)

            partner = request.env['res.partner'].sudo().browse(partner_id)
            if not partner.exists():
                return request.make_json_response({
                    'success': False,
                    'error': 'Partner not found'
                }, status=404)

            result = partner.read(field_list)[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/partner_create', type='http', auth='public', methods=['POST'], csrf=False)
    def partner_create(self, **kwargs):
        """Create a new partner"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'partner_create')
            data = json.loads(request.httprequest.data)
            values = data.get('values')

            if not values or not values.get('name'):
                return request.make_json_response({
                    'success': False,
                    'error': 'values with name is required'
                }, status=400)

            partner = request.env['res.partner'].sudo().create(values)
            result = partner.read(['name', 'email', 'phone', 'mobile', 'company_id', 'is_company', 'vat'])[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/partner_write', type='http', auth='public', methods=['POST'], csrf=False)
    def partner_write(self, **kwargs):
        """Update an existing partner"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'partner_write')
            data = json.loads(request.httprequest.data)
            partner_id = data.get('id')
            values = data.get('values')

            if not partner_id or not values:
                return request.make_json_response({
                    'success': False,
                    'error': 'id and values are required'
                }, status=400)

            partner = request.env['res.partner'].sudo().browse(partner_id)
            if not partner.exists():
                return request.make_json_response({
                    'success': False,
                    'error': 'Partner not found'
                }, status=404)

            partner.write(values)
            result = partner.read(['name', 'email', 'phone', 'mobile', 'company_id', 'is_company', 'vat'])[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    # ─── Sales Report endpoint ──────────────────────────────────

    @http.route('/mcp/call/sale_report', type='http', auth='public', methods=['POST'], csrf=False)
    def sale_report(self, **kwargs):
        """Generate sales report aggregated by salesperson, team, and/or time period."""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'sale_report')
            data = json.loads(request.httprequest.data)

            date_from = data.get('date_from')
            date_to = data.get('date_to')
            group_by_raw = data.get('group_by', 'month,salesperson')
            states = data.get('states', ['sale', 'done'])
            limit = data.get('limit', 500)

            domain = [('state', 'in', states)]
            if date_from:
                domain.append(('date_order', '>=', date_from))
            if date_to:
                domain.append(('date_order', '<=', date_to + ' 23:59:59'))

            SO = request.env['sale.order'].sudo()
            group_keys = [g.strip() for g in group_by_raw.split(',')]

            # If product grouping is needed, aggregate from order lines via read_group
            if 'product' in group_keys:
                line_domain = [('order_id.state', 'in', states)]
                if date_from:
                    line_domain.append(('order_id.date_order', '>=', date_from))
                if date_to:
                    line_domain.append(('order_id.date_order', '<=', date_to + ' 23:59:59'))

                SOL = request.env['sale.order.line'].sudo()
                # Build read_group fields and groupby
                rg_fields = ['price_subtotal', 'product_uom_qty']
                rg_groupby = []
                other_keys = [k for k in group_keys if k != 'product']

                for gk in other_keys:
                    if gk == 'salesperson':
                        rg_fields.append('order_id.user_id')
                        rg_groupby.append('order_id')
                    elif gk == 'team':
                        rg_fields.append('order_id.team_id')
                        rg_groupby.append('order_id')
                    elif gk == 'month':
                        rg_fields.append('order_id.date_order')
                        rg_groupby.append('order_id')
                    elif gk == 'week':
                        rg_fields.append('order_id.date_order')
                        rg_groupby.append('order_id')

                # Always group by product
                rg_fields.append('product_id')
                rg_groupby.append('product_id')

                # Use read_group on sale.order.line
                grouped = SOL.read_group(
                    line_domain,
                    ['price_subtotal:sum', 'product_uom_qty:sum'],
                    ['product_id'],
                    limit=limit,
                )

                # For multi-group (product + time/salesperson/team), we need order-level read_group too
                # Fetch orders for the supporting dimensions
                orders = SO.search(domain, limit=limit)
                if not orders:
                    return request.make_json_response({
                        'success': True,
                        'data': [],
                        'summary': {'order_count': 0, 'total_amount': 0.0},
                    })

                # Build caches
                user_ids = list(set(orders.mapped('user_id.id')))
                team_ids = list(set(orders.mapped('team_id.id')))
                users = {u.id: u.name for u in request.env['res.users'].sudo().browse(user_ids)}
                teams = {t.id: t.name for t in request.env['crm.team'].sudo().browse(team_ids)}

                # Do line-level read with product + order info for aggregation
                lines = SOL.search(line_domain, limit=limit * 10)
                line_data = lines.read(['product_id', 'price_subtotal', 'product_uom_qty', 'order_id'])
                order_data = orders.read(['user_id', 'team_id', 'date_order', 'amount_untaxed', 'amount_total'])
                order_map = {}
                for od in order_data:
                    oid = od['id']
                    d = od.get('date_order', '')
                    order_map[oid] = {
                        'salesperson': users.get(od['user_id'][0] if isinstance(od['user_id'], (list, tuple)) else od['user_id'], ''),
                        'team': teams.get(od['team_id'][0] if isinstance(od['team_id'], (list, tuple)) else od['team_id'], ''),
                        'month': str(d)[:7] if d else '',
                        'week': d.strftime('%Y-W%W') if hasattr(d, 'strftime') and d else str(d)[:10],
                        'amount_untaxed': od['amount_untaxed'],
                        'amount_total': od['amount_total'],
                    }

                # Build aggregation buckets
                from collections import OrderedDict
                buckets = OrderedDict()
                for ld in line_data:
                    pid = ld['product_id'][0] if isinstance(ld['product_id'], (list, tuple)) else ld['product_id']
                    pname = ld['product_id'][1] if isinstance(ld['product_id'], (list, tuple)) else str(ld['product_id'])
                    oid = ld['order_id'][0] if isinstance(ld['order_id'], (list, tuple)) else ld['order_id']
                    oinfo = order_map.get(oid, {})

                    key_parts = []
                    row_base = {}
                    for gk in group_keys:
                        if gk == 'product':
                            key_parts.append(pname)
                            row_base['product'] = pname
                        elif gk == 'salesperson':
                            val = oinfo.get('salesperson', '')
                            key_parts.append(val)
                            row_base['salesperson'] = val
                        elif gk == 'team':
                            val = oinfo.get('team', '')
                            key_parts.append(val)
                            row_base['team'] = val
                        elif gk == 'month':
                            val = oinfo.get('month', '')
                            key_parts.append(val)
                            row_base['month'] = val
                        elif gk == 'week':
                            val = oinfo.get('week', '')
                            key_parts.append(val)
                            row_base['week'] = val
                    key = ' | '.join(key_parts)

                    if key not in buckets:
                        bucket = dict(row_base)
                        bucket['price_subtotal'] = 0.0
                        bucket['product_uom_qty'] = 0.0
                        bucket['order_count'] = 0
                        buckets[key] = bucket
                    buckets[key]['price_subtotal'] += ld.get('price_subtotal', 0)
                    buckets[key]['product_uom_qty'] += ld.get('product_uom_qty', 0)
                    buckets[key]['order_count'] += 1

                result = []
                for b in buckets.values():
                    b['price_subtotal'] = round(b['price_subtotal'], 2)
                    b['product_uom_qty'] = round(b['product_uom_qty'], 2)
                    result.append(b)
                result = result[:limit]

                total_untaxed = round(sum(o['amount_untaxed'] for o in order_map.values()), 2)
                total_total = round(sum(o['amount_total'] for o in order_map.values()), 2)

                return request.make_json_response({
                    'success': True,
                    'data': result,
                    'summary': {
                        'order_count': len(orders),
                        'total_amount_untaxed': total_untaxed,
                        'total_amount_total': total_total,
                        'group_by': group_keys,
                        'date_from': date_from,
                        'date_to': date_to,
                        'states': states,
                    },
                })

            # Non-product grouping — use read_group on sale.order
            rg_fields = ['amount_untaxed:sum', 'amount_total:sum']
            rg_groupby = []
            for gk in group_keys:
                if gk == 'salesperson':
                    rg_groupby.append('user_id')
                elif gk == 'team':
                    rg_groupby.append('team_id')
                elif gk == 'month':
                    rg_groupby.append('date_order:month')
                elif gk == 'week':
                    rg_groupby.append('date_order:week')

            # Fallback: if no recognized groupby, just read orders
            if not rg_groupby:
                orders = SO.search(domain, limit=limit)
                order_data = orders.read(['name', 'date_order', 'partner_id', 'user_id', 'team_id',
                                          'amount_untaxed', 'amount_total', 'state', 'company_id'])
                total_untaxed = round(sum(o['amount_untaxed'] for o in order_data), 2)
                total_total = round(sum(o['amount_total'] for o in order_data), 2)
                return request.make_json_response({
                    'success': True,
                    'data': order_data,
                    'summary': {
                        'order_count': len(order_data),
                        'total_amount_untaxed': total_untaxed,
                        'total_amount_total': total_total,
                        'group_by': group_keys,
                        'date_from': date_from,
                        'date_to': date_to,
                        'states': states,
                    },
                })

            # Use the first groupby for read_group (multi-groupby handled in Python for simplicity)
            primary = rg_groupby[0]
            grouped = SO.read_group(domain, ['amount_untaxed:sum', 'amount_total:sum'], [primary], limit=limit)

            result = []
            for row in grouped:
                entry = {
                    'order_count': row.get(primary + '_count', row.get('__count', 0)),
                    'amount_untaxed': round(row.get('amount_untaxed', 0), 2),
                    'amount_total': round(row.get('amount_total', 0), 2),
                }
                # Label the group
                label = row.get(primary)
                if isinstance(label, (list, tuple)):
                    label = label[1]
                gk = group_keys[0]
                if gk == 'salesperson':
                    entry['salesperson'] = label
                elif gk == 'team':
                    entry['team'] = label
                elif gk in ('month', 'week'):
                    entry[gk] = str(label)
                result.append(entry)

            total_untaxed = round(sum(r['amount_untaxed'] for r in result), 2)
            total_total = round(sum(r['amount_total'] for r in result), 2)

            return request.make_json_response({
                'success': True,
                'data': result,
                'summary': {
                    'order_count': sum(r.get('order_count', 0) for r in result),
                    'total_amount_untaxed': total_untaxed,
                    'total_amount_total': total_total,
                    'group_by': group_keys,
                    'date_from': date_from,
                    'date_to': date_to,
                    'states': states,
                },
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    def _aggregate_rows(self, rows, group_keys):
        """Aggregate rows by the specified group keys, summing numeric fields."""
        from collections import OrderedDict

        numeric_fields = ['amount_untaxed', 'amount_total', 'price_subtotal', 'product_uom_qty']

        buckets = OrderedDict()
        for row in rows:
            key_parts = []
            for gk in group_keys:
                key_parts.append(str(row.get(gk, '')))
            key = ' | '.join(key_parts)

            if key not in buckets:
                bucket = {gk: row.get(gk, '') for gk in group_keys}
                for nf in numeric_fields:
                    bucket[nf] = 0.0
                bucket['order_count'] = 0
                buckets[key] = bucket

            bucket = buckets[key]
            bucket['order_count'] += 1
            for nf in numeric_fields:
                bucket[nf] += row.get(nf, 0.0)

        # Round
        for bucket in buckets.values():
            for nf in numeric_fields:
                bucket[nf] = round(bucket[nf], 2)

        return list(buckets.values())

    # ─── Accounting Audit endpoints ─────────────────────────────

    @http.route('/mcp/call/accounting_audit', type='http', auth='public', methods=['POST'], csrf=False)
    def accounting_audit(self, **kwargs):
        """Run accounting audit checks on posted and draft journal entries."""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'accounting_audit')
            data = json.loads(request.httprequest.data)

            date_from = data.get('date_from')
            date_to = data.get('date_to')
            checks = data.get('checks', ['unbalanced', 'date_mismatch', 'stale_draft', 'suspicious_amount'])
            limit = data.get('limit', 100)

            Move = request.env['account.move'].sudo()
            MoveLine = request.env['account.move.line'].sudo()
            results = {}

            base_domain = []
            if date_from:
                base_domain.append(('date', '>=', date_from))
            if date_to:
                base_domain.append(('date', '<=', date_to))

            # 1) Unbalanced moves — use read_group to find moves where sum(debit) != sum(credit)
            if 'unbalanced' in checks:
                domain = list(base_domain) + [('state', '=', 'posted')]
                # read_group by move_id to get debit/credit sums per move
                move_sums = MoveLine.read_group(
                    [('parent_state', '=', 'posted')] + [
                        d for d in base_domain
                    ],
                    ['debit:sum', 'credit:sum', 'move_id'],
                    ['move_id'],
                    limit=limit,
                )
                issues = []
                move_ids_to_check = []
                for row in move_sums:
                    diff = round(row['debit'] - row['credit'], 2)
                    if diff != 0.0:
                        move_ids_to_check.append(row['move_id'][0])

                if move_ids_to_check:
                    moves = Move.browse(move_ids_to_check).read(
                        ['id', 'name', 'date', 'journal_id', 'partner_id'])
                    # Rebuild diff map
                    diff_map = {}
                    for row in move_sums:
                        if round(row['debit'] - row['credit'], 2) != 0.0:
                            diff_map[row['move_id'][0]] = {
                                'debit': round(row['debit'], 2),
                                'credit': round(row['credit'], 2),
                                'diff': round(row['debit'] - row['credit'], 2),
                            }
                    for md in moves:
                        mid = md['id']
                        dm = diff_map.get(mid, {})
                        issues.append({
                            'move_id': mid,
                            'move_name': md['name'],
                            'date': str(md['date']),
                            'journal': md['journal_id'][1] if isinstance(md['journal_id'], (list, tuple)) else '',
                            'partner': md['partner_id'][1] if isinstance(md['partner_id'], (list, tuple)) else '',
                            'total_debit': dm.get('debit', 0),
                            'total_credit': dm.get('credit', 0),
                            'difference': dm.get('diff', 0),
                        })

                results['unbalanced'] = {
                    'issue_count': len(issues),
                    'issues': issues[:limit],
                }

            # 2) Date mismatch — use read_group to find moves with lines having different dates
            if 'date_mismatch' in checks:
                # Find move lines where line date != move date
                domain_lines = [('parent_state', '=', 'posted')]
                if date_from:
                    domain_lines.append(('date', '>=', date_from))
                if date_to:
                    domain_lines.append(('date', '<=', date_to))

                lines = MoveLine.search(domain_lines, limit=limit * 5)
                issues = []
                seen_move_ids = set()
                # Batch read move dates
                move_ids = list(set(lines.mapped('move_id.id')))
                moves_data = {m['id']: m['date'] for m in Move.browse(move_ids).read(['id', 'date'])}
                lines_data = lines.read(['id', 'date', 'move_id', 'account_id', 'journal_id'])

                for ld in lines_data:
                    mid = ld['move_id'][0] if isinstance(ld['move_id'], (list, tuple)) else ld['move_id']
                    if mid in seen_move_ids:
                        continue
                    line_date = ld['date']
                    move_date = moves_data.get(mid)
                    if line_date and move_date and str(line_date) != str(move_date):
                        seen_move_ids.add(mid)
                        issues.append({
                            'move_id': mid,
                            'move_name': ld['move_id'][1] if isinstance(ld['move_id'], (list, tuple)) else '',
                            'move_date': str(move_date),
                            'line_date': str(line_date),
                            'journal': ld['journal_id'][1] if isinstance(ld['journal_id'], (list, tuple)) else '',
                            'account': ld['account_id'][1] if isinstance(ld['account_id'], (list, tuple)) else '',
                        })
                        if len(issues) >= limit:
                            break
                results['date_mismatch'] = {
                    'issue_count': len(issues),
                    'issues': issues,
                }

            # 3) Stale draft — draft entries older than 30 days
            if 'stale_draft' in checks:
                today = odoo_fields.Date.today()
                stale_date = odoo_fields.Date.subtract(today, days=30)
                domain = [('state', '=', 'draft'), ('date', '<=', stale_date)]
                if date_from:
                    domain.append(('date', '>=', date_from))
                if date_to:
                    domain.append(('date', '<=', date_to))
                moves = Move.search(domain, limit=limit, order='date asc')
                issues = []
                # Batch read
                moves_data = moves.read(['id', 'name', 'date', 'journal_id', 'partner_id', 'line_ids'])
                # Get debit sums per move via read_group
                move_line_sums = {}
                if moves:
                    ml_sums = MoveLine.read_group(
                        [('move_id', 'in', moves.ids)],
                        ['debit:sum', 'move_id'],
                        ['move_id'],
                    )
                    for row in ml_sums:
                        move_line_sums[row['move_id'][0]] = round(row['debit'], 2)

                for md in moves_data:
                    days_old = (today - md['date']).days
                    issues.append({
                        'move_id': md['id'],
                        'move_name': md['name'] or '/',
                        'date': str(md['date']),
                        'journal': md['journal_id'][1] if isinstance(md['journal_id'], (list, tuple)) else '',
                        'partner': md['partner_id'][1] if isinstance(md['partner_id'], (list, tuple)) else '',
                        'amount': move_line_sums.get(md['id'], 0),
                        'days_old': days_old,
                    })
                results['stale_draft'] = {
                    'issue_count': len(issues),
                    'issues': issues,
                }

            # 4) Suspicious amount — single-line posted moves or amounts > threshold
            if 'suspicious_amount' in checks:
                domain = list(base_domain) + [('state', '=', 'posted')]
                # Use read_group to find moves with only 1 line (count lines per move)
                line_counts = MoveLine.read_group(
                    [('parent_state', '=', 'posted')] + [
                        d.replace('date', 'date') for d in base_domain
                    ],
                    ['move_id'],
                    ['move_id'],
                    limit=limit * 3,
                )
                single_line_move_ids = [r['move_id'][0] for r in line_counts if r.get('__count', 0) <= 1]

                issues = []
                if single_line_move_ids:
                    moves = Move.browse(single_line_move_ids[:limit]).read(
                        ['id', 'name', 'date', 'journal_id'])
                    line_debits = MoveLine.read_group(
                        [('move_id', 'in', single_line_move_ids)],
                        ['debit:sum', 'credit:sum', 'move_id'],
                        ['move_id'],
                    )
                    debit_map = {r['move_id'][0]: round(r['debit'] + r['credit'], 2) for r in line_debits}
                    for md in moves:
                        issues.append({
                            'move_id': md['id'],
                            'move_name': md['name'],
                            'date': str(md['date']),
                            'journal': md['journal_id'][1] if isinstance(md['journal_id'], (list, tuple)) else '',
                            'reason': 'single_effective_line',
                            'amount': debit_map.get(md['id'], 0),
                        })

                # Large amount ratio check — batch read
                domain_posted = list(base_domain) + [('state', '=', 'posted')]
                moves = Move.search(domain_posted, limit=limit * 3)
                if moves:
                    line_data = MoveLine.read_group(
                        [('move_id', 'in', moves.ids)],
                        ['debit:max', 'debit:sum', 'move_id'],
                        ['move_id'],
                    )
                    for row in line_data:
                        max_d = row.get('debit', 0)
                        cnt = row.get('__count', 1)
                        total_d = row.get('debit', 0)  # sum already since we asked sum
                        avg_d = total_d / max(cnt, 1)
                        if avg_d > 0 and max_d / avg_d > 100:
                            mid = row['move_id'][0]
                            move = Move.browse(mid)
                            issues.append({
                                'move_id': mid,
                                'move_name': row['move_id'][1],
                                'date': '',
                                'journal': '',
                                'reason': 'large_amount_ratio',
                                'max_line': round(max_d, 2),
                                'avg_line': round(avg_d, 2),
                                'ratio': round(max_d / avg_d, 2),
                            })
                        if len(issues) >= limit:
                            break

                results['suspicious_amount'] = {
                    'issue_count': len(issues),
                    'issues': issues[:limit],
                }

            total_issues = sum(r.get('issue_count', 0) for r in results.values())

            return request.make_json_response({
                'success': True,
                'data': results,
                'summary': {
                    'total_issues': total_issues,
                    'checks_run': checks,
                    'date_from': date_from,
                    'date_to': date_to,
                },
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/gl_report', type='http', auth='public', methods=['POST'], csrf=False)
    def gl_report(self, **kwargs):
        """General Ledger report with opening balance, movements, and closing balance."""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'gl_report')
            data = json.loads(request.httprequest.data)

            date_from = data.get('date_from')
            date_to = data.get('date_to')
            account_codes = data.get('account_codes')
            group_by = data.get('group_by', 'account')
            limit = data.get('limit', 500)

            if not date_from or not date_to:
                return request.make_json_response({
                    'success': False,
                    'error': 'date_from and date_to are required',
                }, status=400)

            company_id = request.env.company.id
            MoveLine = request.env['account.move.line'].sudo()

            # Build account domain
            account_domain = [('company_id', '=', company_id)]
            if account_codes:
                account_domain.append(('code', 'in', account_codes))
            accounts = request.env['account.account'].sudo().search(account_domain, order='code')
            account_map = {a.id: a for a in accounts}
            account_ids = accounts.ids

            if not account_ids:
                return request.make_json_response({
                    'success': True,
                    'data': [],
                    'summary': {
                        'date_from': date_from,
                        'date_to': date_to,
                        'group_by': group_by,
                        'account_count': 0,
                        'row_count': 0,
                    },
                })

            base_domain = [('account_id', 'in', account_ids), ('parent_state', '=', 'posted')]

            # Opening balances — single read_group for all accounts
            opening_domain = base_domain + [('date', '<', date_from)]
            opening_data = MoveLine.read_group(
                opening_domain,
                ['debit', 'credit', 'account_id'],
                ['account_id'],
            )
            opening_map = {}
            for row in opening_data:
                aid = row['account_id'][0]
                opening_map[aid] = round(row['debit'] - row['credit'], 2)

            # Period movements — single read_group for all accounts
            period_domain = base_domain + [('date', '>=', date_from), ('date', '<=', date_to)]
            period_data = MoveLine.read_group(
                period_domain,
                ['debit', 'credit', 'account_id'],
                ['account_id'],
            )
            period_map = {}
            for row in period_data:
                aid = row['account_id'][0]
                period_map[aid] = {
                    'debit': round(row['debit'], 2),
                    'credit': round(row['credit'], 2),
                    'balance': round(row['debit'] - row['credit'], 2),
                }

            # Period line counts per account
            period_count_data = MoveLine.read_group(
                period_domain,
                ['account_id'],
                ['account_id'],
            )
            count_map = {row['account_id'][0]: row['account_id_count'] for row in period_count_data}

            result = []

            if group_by == 'account':
                for account in accounts:
                    op = opening_map.get(account.id, 0)
                    pm = period_map.get(account.id, {'debit': 0, 'credit': 0, 'balance': 0})
                    if op != 0 or pm['debit'] != 0 or pm['credit'] != 0:
                        result.append({
                            'account_code': account.code,
                            'account_name': account.name,
                            'account_type': account.account_type,
                            'opening_balance': op,
                            'period_debit': pm['debit'],
                            'period_credit': pm['credit'],
                            'period_balance': pm['balance'],
                            'closing_balance': round(op + pm['balance'], 2),
                            'line_count': count_map.get(account.id, 0),
                        })

            elif group_by == 'account_partner':
                # read_group by account + partner for both periods
                opening_partner = MoveLine.read_group(
                    opening_domain,
                    ['debit', 'credit', 'account_id', 'partner_id'],
                    ['account_id', 'partner_id'],
                )
                op_partner_map = {}
                for row in opening_partner:
                    key = (row['account_id'][0], row['partner_id'][0])
                    op_partner_map[key] = round(row['debit'] - row['credit'], 2)

                period_partner = MoveLine.read_group(
                    period_domain,
                    ['debit', 'credit', 'account_id', 'partner_id'],
                    ['account_id', 'partner_id'],
                )
                # Collect all partner ids for batch read
                partner_ids = set()
                pp_map = {}
                for row in period_partner:
                    aid, pid = row['account_id'][0], row['partner_id'][0]
                    pp_map[(aid, pid)] = {
                        'debit': round(row['debit'], 2),
                        'credit': round(row['credit'], 2),
                        'balance': round(row['debit'] - row['credit'], 2),
                        'count': row.get('__count', 0),
                    }
                    partner_ids.add(pid)
                for key in op_partner_map:
                    partner_ids.add(key[1])

                partners = request.env['res.partner'].sudo().browse(list(partner_ids)).read(['id', 'name'])
                partner_name_map = {p['id']: p['name'] for p in partners}

                all_keys = set(op_partner_map.keys()) | set(pp_map.keys())
                for account in accounts:
                    for aid, pid in all_keys:
                        if aid != account.id:
                            continue
                        op = op_partner_map.get((aid, pid), 0)
                        pm = pp_map.get((aid, pid), {'debit': 0, 'credit': 0, 'balance': 0, 'count': 0})
                        if op != 0 or pm['debit'] != 0 or pm['credit'] != 0:
                            result.append({
                                'account_code': account.code,
                                'account_name': account.name,
                                'partner': partner_name_map.get(pid, ''),
                                'opening_balance': round(op, 2),
                                'period_debit': pm['debit'],
                                'period_credit': pm['credit'],
                                'period_balance': pm['balance'],
                                'closing_balance': round(op + pm['balance'], 2),
                                'line_count': pm['count'],
                            })

            elif group_by == 'account_journal':
                opening_journal = MoveLine.read_group(
                    opening_domain,
                    ['debit', 'credit', 'account_id', 'journal_id'],
                    ['account_id', 'journal_id'],
                )
                op_journal_map = {}
                for row in opening_journal:
                    key = (row['account_id'][0], row['journal_id'][0])
                    op_journal_map[key] = round(row['debit'] - row['credit'], 2)

                period_journal = MoveLine.read_group(
                    period_domain,
                    ['debit', 'credit', 'account_id', 'journal_id'],
                    ['account_id', 'journal_id'],
                )
                journal_ids = set()
                pj_map = {}
                for row in period_journal:
                    aid, jid = row['account_id'][0], row['journal_id'][0]
                    pj_map[(aid, jid)] = {
                        'debit': round(row['debit'], 2),
                        'credit': round(row['credit'], 2),
                        'balance': round(row['debit'] - row['credit'], 2),
                        'count': row.get('__count', 0),
                    }
                    journal_ids.add(jid)
                for key in op_journal_map:
                    journal_ids.add(key[1])

                journals = request.env['account.journal'].sudo().browse(list(journal_ids)).read(['id', 'name'])
                journal_name_map = {j['id']: j['name'] for j in journals}

                all_keys = set(op_journal_map.keys()) | set(pj_map.keys())
                for account in accounts:
                    for aid, jid in all_keys:
                        if aid != account.id:
                            continue
                        op = op_journal_map.get((aid, jid), 0)
                        pm = pj_map.get((aid, jid), {'debit': 0, 'credit': 0, 'balance': 0, 'count': 0})
                        if op != 0 or pm['debit'] != 0 or pm['credit'] != 0:
                            result.append({
                                'account_code': account.code,
                                'account_name': account.name,
                                'journal': journal_name_map.get(jid, ''),
                                'opening_balance': round(op, 2),
                                'period_debit': pm['debit'],
                                'period_credit': pm['credit'],
                                'period_balance': pm['balance'],
                                'closing_balance': round(op + pm['balance'], 2),
                                'line_count': pm['count'],
                            })

            result = result[:limit]

            return request.make_json_response({
                'success': True,
                'data': result,
                'summary': {
                    'date_from': date_from,
                    'date_to': date_to,
                    'group_by': group_by,
                    'account_count': len(accounts),
                    'row_count': len(result),
                },
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/gl_variance', type='http', auth='public', methods=['POST'], csrf=False)
    def gl_variance(self, **kwargs):
        """Compare GL balances between two periods to detect unexpected variances."""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'gl_variance')
            data = json.loads(request.httprequest.data)

            p1_from = data.get('period1_from')
            p1_to = data.get('period1_to')
            p2_from = data.get('period2_from')
            p2_to = data.get('period2_to')
            threshold = data.get('variance_threshold', 0.01)
            account_codes = data.get('account_codes')

            if not all([p1_from, p1_to, p2_from, p2_to]):
                return request.make_json_response({
                    'success': False,
                    'error': 'period1_from, period1_to, period2_from, period2_to are required',
                }, status=400)

            company_id = request.env.company.id
            MoveLine = request.env['account.move.line'].sudo()

            account_domain = [('company_id', '=', company_id)]
            if account_codes:
                account_domain.append(('code', 'in', account_codes))
            accounts = request.env['account.account'].sudo().search(account_domain, order='code')
            account_ids = accounts.ids

            if not account_ids:
                return request.make_json_response({
                    'success': True,
                    'data': [],
                    'summary': {
                        'period1': {'from': p1_from, 'to': p1_to},
                        'period2': {'from': p2_from, 'to': p2_to},
                        'variance_threshold': threshold,
                        'accounts_checked': 0,
                        'accounts_with_variance': 0,
                        'total_variance': 0,
                    },
                })

            base = [('account_id', 'in', account_ids), ('parent_state', '=', 'posted')]

            # Period 1 — single read_group
            p1_data = MoveLine.read_group(
                base + [('date', '>=', p1_from), ('date', '<=', p1_to)],
                ['debit', 'credit', 'account_id'],
                ['account_id'],
            )
            p1_map = {}
            for row in p1_data:
                p1_map[row['account_id'][0]] = round(row['debit'] - row['credit'], 2)

            # Period 2 — single read_group
            p2_data = MoveLine.read_group(
                base + [('date', '>=', p2_from), ('date', '<=', p2_to)],
                ['debit', 'credit', 'account_id'],
                ['account_id'],
            )
            p2_map = {}
            for row in p2_data:
                p2_map[row['account_id'][0]] = round(row['debit'] - row['credit'], 2)

            result = []
            for account in accounts:
                bal1 = p1_map.get(account.id, 0)
                bal2 = p2_map.get(account.id, 0)
                variance = round(bal2 - bal1, 2)
                pct_change = round((variance / bal1) * 100, 2) if bal1 != 0 else 0.0

                if abs(variance) >= threshold:
                    result.append({
                        'account_code': account.code,
                        'account_name': account.name,
                        'account_type': account.account_type,
                        'period1_balance': bal1,
                        'period2_balance': bal2,
                        'variance': variance,
                        'variance_pct': pct_change,
                    })

            return request.make_json_response({
                'success': True,
                'data': result,
                'summary': {
                    'period1': {'from': p1_from, 'to': p1_to},
                    'period2': {'from': p2_from, 'to': p2_to},
                    'variance_threshold': threshold,
                    'accounts_checked': len(accounts),
                    'accounts_with_variance': len(result),
                    'total_variance': round(sum(r['variance'] for r in result), 2),
                },
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/account_move_search', type='http', auth='public', methods=['POST'], csrf=False)
    def account_move_search(self, **kwargs):
        """Search journal entries with optional line details."""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'account_move_search')
            data = json.loads(request.httprequest.data)
            domain = data.get('domain', [])
            field_list = data.get('fields', ['name', 'date', 'journal_id', 'partner_id', 'state', 'move_type', 'amount_total'])
            with_lines = data.get('with_lines', False)
            limit = data.get('limit', 80)

            moves = request.env['account.move'].sudo().search(domain, limit=limit)
            result = []
            line_fields = ['account_id', 'partner_id', 'name', 'debit', 'credit', 'date', 'date_maturity', 'reconciled']

            for move in moves:
                move_data = move.read(field_list)[0]
                if with_lines:
                    move_data['lines'] = move.line_ids.read(line_fields)
                result.append(move_data)

            return request.make_json_response({
                'success': True,
                'data': result,
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    # ─── Purchase Order endpoints ──────────────────────────────

    @http.route('/mcp/call/purchase_order_search', type='http', auth='public', methods=['POST'], csrf=False)
    def purchase_order_search(self, **kwargs):
        """Search for purchase orders with optional filters"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'purchase_order_search')
            data = json.loads(request.httprequest.data)
            domain = data.get('domain', [])
            field_list = data.get('fields', ['name', 'partner_id', 'date_order', 'date_planned', 'amount_total', 'amount_untaxed', 'state', 'invoice_status', 'currency_id', 'company_id', 'user_id', 'origin'])
            limit = data.get('limit', 80)

            orders = request.env['purchase.order'].sudo().search(domain, limit=limit)
            result = orders.read(field_list)

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/purchase_order_read', type='http', auth='public', methods=['POST'], csrf=False)
    def purchase_order_read(self, **kwargs):
        """Read a specific purchase order by ID"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'purchase_order_read')
            data = json.loads(request.httprequest.data)
            order_id = data.get('id')
            field_list = data.get('fields', ['name', 'partner_id', 'date_order', 'date_planned', 'amount_total', 'amount_untaxed', 'state', 'invoice_status', 'currency_id', 'company_id', 'user_id', 'origin', 'order_line', 'picking_count', 'invoice_count'])

            if not order_id:
                return request.make_json_response({
                    'success': False,
                    'error': 'id is required'
                }, status=400)

            order = request.env['purchase.order'].sudo().browse(order_id)
            if not order.exists():
                return request.make_json_response({
                    'success': False,
                    'error': 'Purchase order not found'
                }, status=404)

            result = order.read(field_list)[0]

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/budget_report', type='http', auth='public', methods=['POST'], csrf=False)
    def budget_report(self, **kwargs):
        """Search budget report by department, plan, or period"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'budget_report')
            data = json.loads(request.httprequest.data)
            department_id = data.get('department_id')
            plan_id = data.get('plan_id')
            analytic_account_id = data.get('analytic_account_id')
            year = data.get('year')
            month = data.get('month')
            limit = data.get('limit', 80)

            domain = []
            if department_id:
                domain.append(('department_id', '=', department_id))
            if plan_id:
                domain.append(('plan_id', '=', plan_id))
            if analytic_account_id:
                domain.append(('analytic_account_id', '=', analytic_account_id))
            if year:
                domain.append(('date', '>=', '%s-01-01' % year))
                domain.append(('date', '<=', '%s-12-31' % year))
            if month:
                domain.append(('date', 'like', '-%s-' % month))

            field_list = data.get('fields', [
                'budget_line_id', 'plan_id', 'analytic_account_id',
                'department_id', 'project_id', 'category', 'entry_type',
                'name', 'amount', 'date', 'budget_amt', 'actual_amt',
                'remaining_amt', 'utilization',
            ])

            records = request.env['monthly.budget.report'].sudo().search(domain, limit=limit)
            result = records.read(field_list)

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)
    @http.route('/mcp/call/refresh_budget_mv', type='http', auth='public', methods=['POST'], csrf=False)
    def refresh_budget_mv(self, **kwargs):
        """Recreate and refresh the budget report materialized view"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'refresh_budget_mv')
            BudgetReport = request.env['monthly.budget.report'].sudo()
            BudgetReport.init()
            return request.make_json_response({
                'success': True,
                'data': {'message': 'Budget report materialized view recreated and refreshed'}
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)
    # ─── Company endpoints ──────────────────────────────────────

    @http.route('/mcp/call/stock_valuation_layer_search', type='http', auth='public', methods=['POST'], csrf=False)
    def stock_valuation_layer_search(self, **kwargs):
        """Search for stock valuation layers with optional filters"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'stock_valuation_layer_search')
            data = json.loads(request.httprequest.data)
            domain = data.get('domain', [])
            field_list = data.get('fields', ['id', 'stock_move_id', 'product_id', 'quantity', 'unit_cost', 'value', 'remaining_qty', 'remaining_value', 'warehouse_id', 'company_id', 'create_date'])
            limit = data.get('limit', 80)

            layers = request.env['stock.valuation.layer'].sudo().search(domain, limit=limit)
            result = layers.read(field_list)

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/stock_valuation_layer_read', type='http', auth='public', methods=['POST'], csrf=False)
    def stock_valuation_layer_read(self, **kwargs):
        """Read a specific stock valuation layer by ID"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'stock_valuation_layer_read')
            data = json.loads(request.httprequest.data)
            layer_id = data.get('id')
            field_list = data.get('fields', ['id', 'stock_move_id', 'product_id', 'quantity', 'unit_cost', 'value', 'remaining_qty', 'remaining_value', 'warehouse_id', 'company_id', 'create_date'])

            if not layer_id:
                return request.make_json_response({
                    'success': False,
                    'error': 'id is required'
                }, status=400)

            layer = request.env['stock.valuation.layer'].sudo().browse(layer_id)
            if not layer.exists():
                return request.make_json_response({
                    'success': False,
                    'error': 'Stock valuation layer not found'
                }, status=404)

            result = layer.read(field_list)
            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/stock_move_search', type='http', auth='public', methods=['POST'], csrf=False)
    def stock_move_search(self, **kwargs):
        """Search for stock moves with optional filters"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'stock_move_search')
            data = json.loads(request.httprequest.data)
            domain = data.get('domain', [])
            field_list = data.get('fields', ['id', 'name', 'product_id', 'product_qty', 'product_uom', 'date', 'state', 'location_id', 'location_dest_id', 'picking_type_id', 'reference', 'partner_id', 'origin', 'company_id'])
            limit = data.get('limit', 80)

            moves = request.env['stock.move'].sudo().search(domain, limit=limit)
            result = moves.read(field_list)

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/company_list', type='http', auth='public', methods=['POST'], csrf=False)
    def company_list(self, **kwargs):
        """List all active companies"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'company_list')
            data = json.loads(request.httprequest.data)
            field_list = data.get('fields', ['name', 'currency_id', 'partner_id', 'vat', 'email', 'phone'])

            companies = request.env['res.company'].sudo().search([('active', '=', True)])
            result = companies.read(field_list)

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)

    @http.route('/mcp/call/company_search', type='http', auth='public', methods=['POST'], csrf=False)
    def company_search(self, **kwargs):
        """Search for companies with optional filters"""
        try:
            key_record = self._verify_api_key()
            self._check_policy(key_record, 'company_search')
            data = json.loads(request.httprequest.data)
            domain = data.get('domain', [])
            field_list = data.get('fields', ['name', 'currency_id', 'partner_id', 'vat', 'email', 'phone'])
            limit = data.get('limit', 80)

            companies = request.env['res.company'].sudo().search(domain, limit=limit)
            result = companies.read(field_list)

            return request.make_json_response({
                'success': True,
                'data': result
            })
        except AccessDenied as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=401)
        except Exception as e:
            return request.make_json_response({
                'success': False,
                'error': str(e)
            }, status=400)
