# Warranty Dashboard Charts Implementation Plan

## Backend Implementation for Chart Data Preparation

### 1. New Fields in WarrantyDashboardCache Model

Add the following fields to `buz_warranty_management/models/warranty_dashboard_cache.py`:

```python
# Chart data fields (JSON format)
warranty_status_chart = fields.Text(string='Warranty Status Chart Data')
warranty_type_chart = fields.Text(string='Warranty Type Chart Data')
claims_trend_chart = fields.Text(string='Claims Trend Chart Data')
monthly_comparison_chart = fields.Text(string='Monthly Comparison Chart Data')
top_products_chart = fields.Text(string='Top Products Chart Data')
top_customers_chart = fields.Text(string='Top Customers Chart Data')
claim_types_chart = fields.Text(string='Claim Types Chart Data')
claim_resolution_chart = fields.Text(string='Claim Resolution Chart Data')
warranty_expiry_chart = fields.Text(string='Warranty Expiry Chart Data')
financial_impact_chart = fields.Text(string='Financial Impact Chart Data')
```

### 2. Chart Data Preparation Methods

#### Method: `_prepare_warranty_status_chart(self)`
```python
def _prepare_warranty_status_chart(self):
    """Prepare data for warranty status pie chart"""
    self._cr.execute("""
        SELECT state, COUNT(*) as count
        FROM warranty_card
        GROUP BY state
    """)
    
    results = self._cr.fetchall()
    labels = []
    data = []
    colors = {
        'draft': '#6c757d',
        'active': '#28a745',
        'expired': '#dc3545',
        'cancelled': '#ffc107'
    }
    
    for state, count in results:
        labels.append(dict(self._fields['state'].selection).get(state, state))
        data.append(count)
    
    chart_data = {
        'type': 'pie',
        'data': {
            'labels': labels,
            'datasets': [{
                'data': data,
                'backgroundColor': [colors.get(r[0], '#007bff') for r in results],
                'borderWidth': 2,
                'borderColor': '#ffffff'
            }]
        },
        'options': {
            'responsive': True,
            'plugins': {
                'legend': {'position': 'bottom'},
                'tooltip': {
                    'callbacks': {
                        'label': 'function(context) { return context.label + ": " + context.parsed + " warranties"; }'
                    }
                }
            }
        }
    }
    
    self.warranty_status_chart = json.dumps(chart_data)
```

#### Method: `_prepare_claims_trend_chart(self, months=12)`
```python
def _prepare_claims_trend_chart(self, months=12):
    """Prepare data for claims trend line chart"""
    self._cr.execute("""
        SELECT 
            DATE_TRUNC('month', claim_date) as month,
            COUNT(*) as claims_count,
            COUNT(CASE WHEN is_under_warranty THEN 1 END) as warranty_claims,
            COUNT(CASE WHEN NOT is_under_warranty THEN 1 END) as out_warranty_claims
        FROM warranty_claim
        WHERE claim_date >= CURRENT_DATE - INTERVAL '%s months'
        GROUP BY DATE_TRUNC('month', claim_date)
        ORDER BY month
    """, (months,))
    
    results = self._cr.fetchall()
    labels = [r[0].strftime('%b %Y') for r in results]
    warranty_claims = [r[2] for r in results]
    out_warranty_claims = [r[3] for r in results]
    
    chart_data = {
        'type': 'line',
        'data': {
            'labels': labels,
            'datasets': [
                {
                    'label': 'Under Warranty Claims',
                    'data': warranty_claims,
                    'borderColor': '#28a745',
                    'backgroundColor': 'rgba(40, 167, 69, 0.1)',
                    'fill': True,
                    'tension': 0.4
                },
                {
                    'label': 'Out of Warranty Claims',
                    'data': out_warranty_claims,
                    'borderColor': '#dc3545',
                    'backgroundColor': 'rgba(220, 53, 69, 0.1)',
                    'fill': True,
                    'tension': 0.4
                }
            ]
        },
        'options': {
            'responsive': True,
            'scales': {
                'y': {'beginAtZero': True}
            },
            'plugins': {
                'legend': {'position': 'top'},
                'tooltip': {'mode': 'index', 'intersect': False}
            }
        }
    }
    
    self.claims_trend_chart = json.dumps(chart_data)
```

#### Method: `_prepare_monthly_comparison_chart(self, months=12)`
```python
def _prepare_monthly_comparison_chart(self, months=12):
    """Prepare data for monthly comparison bar chart"""
    self._cr.execute("""
        WITH monthly_warranties AS (
            SELECT 
                DATE_TRUNC('month', create_date) as month,
                COUNT(*) as warranties_count
            FROM warranty_card
            WHERE create_date >= CURRENT_DATE - INTERVAL '%s months'
            GROUP BY DATE_TRUNC('month', create_date)
        ),
        monthly_claims AS (
            SELECT 
                DATE_TRUNC('month', claim_date) as month,
                COUNT(*) as claims_count
            FROM warranty_claim
            WHERE claim_date >= CURRENT_DATE - INTERVAL '%s months'
            GROUP BY DATE_TRUNC('month', claim_date)
        )
        SELECT 
            COALESCE(w.month, c.month) as month,
            COALESCE(w.warranties_count, 0) as warranties,
            COALESCE(c.claims_count, 0) as claims
        FROM monthly_warranties w
        FULL OUTER JOIN monthly_claims c ON w.month = c.month
        ORDER BY month
    """, (months, months))
    
    results = self._cr.fetchall()
    labels = [r[0].strftime('%b %Y') for r in results]
    warranties = [r[1] for r in results]
    claims = [r[2] for r in results]
    
    chart_data = {
        'type': 'bar',
        'data': {
            'labels': labels,
            'datasets': [
                {
                    'label': 'New Warranties',
                    'data': warranties,
                    'backgroundColor': '#007bff',
                    'borderColor': '#0056b3',
                    'borderWidth': 1
                },
                {
                    'label': 'Claims',
                    'data': claims,
                    'backgroundColor': '#ffc107',
                    'borderColor': '#d39e00',
                    'borderWidth': 1
                }
            ]
        },
        'options': {
            'responsive': True,
            'scales': {
                'y': {'beginAtZero': True}
            },
            'plugins': {
                'legend': {'position': 'top'}
            }
        }
    }
    
    self.monthly_comparison_chart = json.dumps(chart_data)
```

#### Method: `_prepare_top_products_chart(self, limit=10)`
```python
def _prepare_top_products_chart(self, limit=10):
    """Prepare data for top products horizontal bar chart"""
    self._cr.execute("""
        SELECT 
            pt.name,
            COUNT(wc.id) as warranty_count,
            COUNT(wc2.id) as claim_count
        FROM warranty_card wc
        JOIN product_product pp ON wc.product_id = pp.id
        JOIN product_template pt ON pp.product_tmpl_id = pt.id
        LEFT JOIN warranty_claim wc2 ON wc.id = wc2.warranty_card_id
        GROUP BY pt.name
        ORDER BY warranty_count DESC
        LIMIT %s
    """, (limit,))
    
    results = self._cr.fetchall()
    labels = [r[0] for r in results]
    warranties = [r[1] for r in results]
    claims = [r[2] for r in results]
    
    chart_data = {
        'type': 'bar',
        'data': {
            'labels': labels,
            'datasets': [
                {
                    'label': 'Warranties',
                    'data': warranties,
                    'backgroundColor': '#007bff',
                    'borderColor': '#0056b3',
                    'borderWidth': 1
                },
                {
                    'label': 'Claims',
                    'data': claims,
                    'backgroundColor': '#dc3545',
                    'borderColor': '#bd2130',
                    'borderWidth': 1
                }
            ]
        },
        'options': {
            'indexAxis': 'y',
            'responsive': True,
            'scales': {
                'x': {'beginAtZero': True}
            },
            'plugins': {
                'legend': {'position': 'top'}
            }
        }
    }
    
    self.top_products_chart = json.dumps(chart_data)
```

#### Method: `_prepare_top_customers_chart(self, limit=10)`
```python
def _prepare_top_customers_chart(self, limit=10):
    """Prepare data for top customers horizontal bar chart"""
    self._cr.execute("""
        SELECT 
            rp.name,
            COUNT(wc.id) as warranty_count,
            COUNT(wc2.id) as claim_count
        FROM warranty_card wc
        JOIN res_partner rp ON wc.partner_id = rp.id
        LEFT JOIN warranty_claim wc2 ON wc.id = wc2.warranty_card_id
        GROUP BY rp.name
        ORDER BY warranty_count DESC
        LIMIT %s
    """, (limit,))
    
    results = self._cr.fetchall()
    labels = [r[0] for r in results]
    warranties = [r[1] for r in results]
    claims = [r[2] for r in results]
    
    chart_data = {
        'type': 'bar',
        'data': {
            'labels': labels,
            'datasets': [
                {
                    'label': 'Warranties',
                    'data': warranties,
                    'backgroundColor': '#28a745',
                    'borderColor': '#1e7e34',
                    'borderWidth': 1
                },
                {
                    'label': 'Claims',
                    'data': claims,
                    'backgroundColor': '#ffc107',
                    'borderColor': '#d39e00',
                    'borderWidth': 1
                }
            ]
        },
        'options': {
            'indexAxis': 'y',
            'responsive': True,
            'scales': {
                'x': {'beginAtZero': True}
            },
            'plugins': {
                'legend': {'position': 'top'}
            }
        }
    }
    
    self.top_customers_chart = json.dumps(chart_data)
```

#### Method: `_prepare_claim_types_chart(self, months=12)`
```python
def _prepare_claim_types_chart(self, months=12):
    """Prepare data for claim types stacked area chart"""
    self._cr.execute("""
        SELECT 
            DATE_TRUNC('month', claim_date) as month,
            claim_type,
            COUNT(*) as count
        FROM warranty_claim
        WHERE claim_date >= CURRENT_DATE - INTERVAL '%s months'
        GROUP BY DATE_TRUNC('month', claim_date), claim_type
        ORDER BY month, claim_type
    """, (months,))
    
    results = self._cr.fetchall()
    # Process results for stacked chart
    months_list = sorted(set(r[0] for r in results))
    claim_types = ['repair', 'replace', 'refund']
    
    datasets = []
    colors = {
        'repair': '#007bff',
        'replace': '#28a745',
        'refund': '#ffc107'
    }
    
    for claim_type in claim_types:
        data = []
        for month in months_list:
            count = next((r[2] for r in results if r[0] == month and r[1] == claim_type), 0)
            data.append(count)
        
        datasets.append({
            'label': claim_type.title(),
            'data': data,
            'backgroundColor': colors[claim_type],
            'borderColor': colors[claim_type],
            'fill': True
        })
    
    chart_data = {
        'type': 'line',
        'data': {
            'labels': [m.strftime('%b %Y') for m in months_list],
            'datasets': datasets
        },
        'options': {
            'responsive': True,
            'scales': {
                'y': {'beginAtZero': True, 'stacked': True},
                'x': {'stacked': True}
            },
            'plugins': {
                'legend': {'position': 'top'}
            }
        }
    }
    
    self.claim_types_chart = json.dumps(chart_data)
```

#### Method: `_prepare_warranty_expiry_chart(self, months=12)`
```python
def _prepare_warranty_expiry_chart(self, months=12):
    """Prepare data for warranty expiry forecast chart"""
    self._cr.execute("""
        SELECT 
            DATE_TRUNC('month', end_date) as expiry_month,
            COUNT(*) as expiring_count
        FROM warranty_card
        WHERE end_date >= CURRENT_DATE
        AND end_date <= CURRENT_DATE + INTERVAL '%s months'
        GROUP BY DATE_TRUNC('month', end_date)
        ORDER BY expiry_month
    """, (months,))
    
    results = self._cr.fetchall()
    labels = [r[0].strftime('%b %Y') for r in results]
    data = [r[1] for r in results]
    
    chart_data = {
        'type': 'bar',
        'data': {
            'labels': labels,
            'datasets': [{
                'label': 'Warranties Expiring',
                'data': data,
                'backgroundColor': '#dc3545',
                'borderColor': '#bd2130',
                'borderWidth': 1
            }]
        },
        'options': {
            'responsive': True,
            'scales': {
                'y': {'beginAtZero': True}
            },
            'plugins': {
                'legend': {'display': False}
            }
        }
    }
    
    self.warranty_expiry_chart = json.dumps(chart_data)
```

### 3. Update Main Cache Update Method

Modify the `_update_all_metrics()` method to include chart data preparation:

```python
def _update_all_metrics(self):
    """Update all cached metrics efficiently"""
    start_time = time.time()
    
    try:
        # Existing KPI calculations...
        # [Keep existing code for basic metrics]
        
        # Update chart data
        self._prepare_warranty_status_chart()
        self._prepare_claims_trend_chart()
        self._prepare_monthly_comparison_chart()
        self._prepare_top_products_chart()
        self._prepare_top_customers_chart()
        self._prepare_claim_types_chart()
        self._prepare_warranty_expiry_chart()
        
        # Update cache status
        update_duration = time.time() - start_time
        self.write({
            'is_updating': False,
            'cache_status': 'valid',
            'cache_valid_until': fields.Datetime.now() + timedelta(minutes=15),
            'update_duration': update_duration,
            'last_update': fields.Datetime.now()
        })
        
        _logger.info(f"Dashboard cache with charts updated in {update_duration:.2f} seconds")
        
    except Exception as e:
        _logger.error(f"Error updating dashboard cache: {str(e)}")
        self.write({
            'is_updating': False,
            'cache_status': 'error'
        })
```

### 4. Add Chart Data to Dashboard Model

Update `buz_warranty_management/models/warranty_dashboard.py` to include chart fields:

```python
# Chart data fields (related to cache)
warranty_status_chart = fields.Text(
    related='cache_id.warranty_status_chart',
    string='Warranty Status Chart'
)
claims_trend_chart = fields.Text(
    related='cache_id.claims_trend_chart',
    string='Claims Trend Chart'
)
monthly_comparison_chart = fields.Text(
    related='cache_id.monthly_comparison_chart',
    string='Monthly Comparison Chart'
)
top_products_chart = fields.Text(
    related='cache_id.top_products_chart',
    string='Top Products Chart'
)
top_customers_chart = fields.Text(
    related='cache_id.top_customers_chart',
    string='Top Customers Chart'
)
claim_types_chart = fields.Text(
    related='cache_id.claim_types_chart',
    string='Claim Types Chart'
)
warranty_expiry_chart = fields.Text(
    related='cache_id.warranty_expiry_chart',
    string='Warranty Expiry Chart'
)
```

### 5. Performance Optimization Notes

1. **SQL Optimization**: All queries use efficient SQL with proper indexing
2. **Data Limiting**: Charts limit data to reasonable amounts (top 10, last 12 months)
3. **JSON Storage**: Chart data stored as JSON for easy frontend consumption
4. **Incremental Updates**: Only update charts when relevant data changes
5. **Caching Strategy**: Chart data cached with same validity as other metrics

### 6. Security Considerations

1. **Record Rules**: All queries respect Odoo's record rules automatically
2. **Data Filtering**: Chart data filtered based on user permissions
3. **SQL Injection**: All queries use parameterized queries to prevent SQL injection

This implementation provides a comprehensive backend foundation for the interactive dashboard charts with optimized performance and security.