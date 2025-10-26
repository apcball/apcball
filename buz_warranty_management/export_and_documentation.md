# Chart Export Functionality and Documentation

## 1. Chart Export Implementation

### 1.1 Export Service

Create a dedicated export service for handling chart exports:

```javascript
// In static/src/js/chart_export_service.js
/** @odoo-module **/

import { serviceRegistry } from "@web/core/registry";
import { download } from "@web/core/network/download";

export class ChartExportService {
    constructor(env) {
        this.env = env;
    }
    
    /**
     * Export chart as PNG image
     */
    async exportAsPNG(chartId, filename = null) {
        const chart = this.getChartById(chartId);
        if (!chart) {
            throw new Error(`Chart with ID ${chartId} not found`);
        }
        
        const canvas = chart.canvas;
        const url = canvas.toDataURL('image/png');
        
        const defaultFilename = `${chartId}_${new Date().toISOString().split('T')[0]}.png`;
        filename = filename || defaultFilename;
        
        // Create download link
        const link = document.createElement('a');
        link.download = filename;
        link.href = url;
        link.click();
        
        return { success: true, filename };
    }
    
    /**
     * Export chart as JPG image
     */
    async exportAsJPG(chartId, filename = null) {
        const chart = this.getChartById(chartId);
        if (!chart) {
            throw new Error(`Chart with ID ${chartId} not found`);
        }
        
        const canvas = chart.canvas;
        const url = canvas.toDataURL('image/jpeg', 0.9);
        
        const defaultFilename = `${chartId}_${new Date().toISOString().split('T')[0]}.jpg`;
        filename = filename || defaultFilename;
        
        const link = document.createElement('a');
        link.download = filename;
        link.href = url;
        link.click();
        
        return { success: true, filename };
    }
    
    /**
     * Export chart as PDF (requires jsPDF library)
     */
    async exportAsPDF(chartId, filename = null, options = {}) {
        const chart = this.getChartById(chartId);
        if (!chart) {
            throw new Error(`Chart with ID ${chartId} not found`);
        }
        
        // Load jsPDF if not already loaded
        if (!window.jsPDF) {
            await this.loadJSPLibrary();
        }
        
        const canvas = chart.canvas;
        const imgData = canvas.toDataURL('image/png');
        
        const pdf = new window.jsPDF({
            orientation: options.orientation || 'landscape',
            unit: 'mm',
            format: 'a4'
        });
        
        const imgWidth = 280;
        const pageHeight = pdf.internal.pageSize.height;
        const imgHeight = (canvas.height * imgWidth) / canvas.width;
        let heightLeft = imgHeight;
        let position = 10;
        
        // Add image to PDF
        pdf.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight);
        heightLeft -= pageHeight;
        
        while (heightLeft >= 0) {
            position = heightLeft - imgHeight;
            pdf.addPage();
            pdf.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight);
            heightLeft -= pageHeight;
        }
        
        const defaultFilename = `${chartId}_${new Date().toISOString().split('T')[0]}.pdf`;
        filename = filename || defaultFilename;
        
        pdf.save(filename);
        
        return { success: true, filename };
    }
    
    /**
     * Export chart data as CSV
     */
    async exportDataAsCSV(chartId, filename = null) {
        const chart = this.getChartById(chartId);
        if (!chart) {
            throw new Error(`Chart with ID ${chartId} not found`);
        }
        
        const data = chart.data;
        let csvContent = '';
        
        // Add headers
        const headers = ['Label', ...data.datasets.map(ds => ds.label)];
        csvContent += headers.join(',') + '\n';
        
        // Add data rows
        for (let i = 0; i < data.labels.length; i++) {
            const row = [data.labels[i]];
            for (const dataset of data.datasets) {
                row.push(dataset.data[i] || 0);
            }
            csvContent += row.join(',') + '\n';
        }
        
        const defaultFilename = `${chartId}_data_${new Date().toISOString().split('T')[0]}.csv`;
        filename = filename || defaultFilename;
        
        // Create blob and download
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
        
        return { success: true, filename };
    }
    
    /**
     * Export multiple charts as a combined PDF report
     */
    async exportMultipleChartsAsPDF(chartIds, filename = null) {
        if (!window.jsPDF) {
            await this.loadJSPLibrary();
        }
        
        const pdf = new window.jsPDF({
            orientation: 'landscape',
            unit: 'mm',
            format: 'a4'
        });
        
        for (let i = 0; i < chartIds.length; i++) {
            const chartId = chartIds[i];
            const chart = this.getChartById(chartId);
            
            if (chart) {
                if (i > 0) {
                    pdf.addPage();
                }
                
                // Add chart title
                pdf.setFontSize(16);
                pdf.text(this.getChartTitle(chartId), 10, 10);
                
                // Add chart image
                const canvas = chart.canvas;
                const imgData = canvas.toDataURL('image/png');
                const imgWidth = 280;
                const imgHeight = (canvas.height * imgWidth) / canvas.width;
                
                pdf.addImage(imgData, 'PNG', 10, 20, imgWidth, imgHeight);
            }
        }
        
        const defaultFilename = `warranty_dashboard_${new Date().toISOString().split('T')[0]}.pdf`;
        filename = filename || defaultFilename;
        
        pdf.save(filename);
        
        return { success: true, filename };
    }
    
    /**
     * Get chart instance by ID
     */
    getChartById(chartId) {
        const canvas = document.getElementById(chartId);
        return canvas ? Chart.getChart(canvas) : null;
    }
    
    /**
     * Get chart title from chart ID
     */
    getChartTitle(chartId) {
        const titles = {
            'warranty_status_chart': 'Warranty Status Distribution',
            'claims_trend_chart': 'Claims Trend Analysis',
            'monthly_comparison_chart': 'Monthly Comparison',
            'top_products_chart': 'Top Products',
            'top_customers_chart': 'Top Customers',
            'claim_types_chart': 'Claim Types Analysis',
            'warranty_expiry_chart': 'Warranty Expiry Forecast'
        };
        
        return titles[chartId] || chartId.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
    
    /**
     * Load jsPDF library dynamically
     */
    async loadJSPLibrary() {
        return new Promise((resolve, reject) => {
            if (window.jsPDF) {
                resolve();
                return;
            }
            
            const script = document.createElement('script');
            script.src = '/buz_warranty_management/static/src/lib/jspdf.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
}

// Register the service
export const chartExportService = {
    dependencies: [],
    start(env) {
        return new ChartExportService(env);
    },
};

serviceRegistry.add("chartExport", chartExportService);
```

### 1.2 Export Component

Create an export menu component:

```javascript
// In static/src/js/chart_export_component.js
/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ChartExportMenu extends Component {
    static template = "buz_warranty_management.ChartExportMenu";
    
    setup() {
        this.chartExport = useService("chartExport");
        this.state = {
            showMenu: false,
            exporting: false
        };
    }
    
    async exportAsPNG() {
        this.state.exporting = true;
        try {
            await this.chartExport.exportAsPNG(this.props.chartId);
            this.showNotification('Chart exported as PNG', 'success');
        } catch (error) {
            this.showNotification('Failed to export chart: ' + error.message, 'danger');
        } finally {
            this.state.exporting = false;
            this.state.showMenu = false;
        }
    }
    
    async exportAsJPG() {
        this.state.exporting = true;
        try {
            await this.chartExport.exportAsJPG(this.props.chartId);
            this.showNotification('Chart exported as JPG', 'success');
        } catch (error) {
            this.showNotification('Failed to export chart: ' + error.message, 'danger');
        } finally {
            this.state.exporting = false;
            this.state.showMenu = false;
        }
    }
    
    async exportAsPDF() {
        this.state.exporting = true;
        try {
            await this.chartExport.exportAsPDF(this.props.chartId);
            this.showNotification('Chart exported as PDF', 'success');
        } catch (error) {
            this.showNotification('Failed to export chart: ' + error.message, 'danger');
        } finally {
            this.state.exporting = false;
            this.state.showMenu = false;
        }
    }
    
    async exportDataAsCSV() {
        this.state.exporting = true;
        try {
            await this.chartExport.exportDataAsCSV(this.props.chartId);
            this.showNotification('Chart data exported as CSV', 'success');
        } catch (error) {
            this.showNotification('Failed to export data: ' + error.message, 'danger');
        } finally {
            this.state.exporting = false;
            this.state.showMenu = false;
        }
    }
    
    showNotification(message, type) {
        this.env.services.notification.add(message, {
            type: type,
            sticky: false
        });
    }
}
```

### 1.3 Export Template

```xml
<!-- Chart Export Menu Template -->
<t t-name="buz_warranty_management.ChartExportMenu" owl="1">
    <div class="chart-export-menu dropdown">
        <button class="btn btn-sm btn-outline-secondary dropdown-toggle" 
                type="button" 
                data-bs-toggle="dropdown"
                t-att-disabled="state.exporting">
            <i class="fa fa-download me-1"/>
            <t t-if="state.exporting">Exporting...</t>
            <t t-else="">Export</t>
        </button>
        
        <ul class="dropdown-menu">
            <li>
                <a class="dropdown-item" href="#" t-on-click="exportAsPNG">
                    <i class="fa fa-image me-2"/> Export as PNG
                </a>
            </li>
            <li>
                <a class="dropdown-item" href="#" t-on-click="exportAsJPG">
                    <i class="fa fa-image me-2"/> Export as JPG
                </a>
            </li>
            <li>
                <a class="dropdown-item" href="#" t-on-click="exportAsPDF">
                    <i class="fa fa-file-pdf-o me-2"/> Export as PDF
                </a>
            </li>
            <li><hr class="dropdown-divider"/></li>
            <li>
                <a class="dropdown-item" href="#" t-on-click="exportDataAsCSV">
                    <i class="fa fa-table me-2"/> Export Data (CSV)
                </a>
            </li>
        </ul>
    </div>
</t>
```

### 1.4 Batch Export Functionality

```javascript
// Batch export for all charts
export class DashboardBatchExport extends Component {
    static template = "buz_warranty_management.DashboardBatchExport";
    
    setup() {
        this.chartExport = useService("chartExport");
        this.state = {
            exporting: false,
            selectedCharts: []
        };
    }
    
    async exportAllCharts() {
        this.state.exporting = true;
        try {
            const chartIds = [
                'warranty_status_chart',
                'claims_trend_chart',
                'monthly_comparison_chart',
                'top_products_chart',
                'top_customers_chart',
                'claim_types_chart',
                'warranty_expiry_chart'
            ];
            
            await this.chartExport.exportMultipleChartsAsPDF(chartIds);
            this.showNotification('All charts exported as PDF report', 'success');
        } catch (error) {
            this.showNotification('Failed to export charts: ' + error.message, 'danger');
        } finally {
            this.state.exporting = false;
        }
    }
    
    async exportSelectedCharts() {
        if (this.state.selectedCharts.length === 0) {
            this.showNotification('Please select at least one chart', 'warning');
            return;
        }
        
        this.state.exporting = true;
        try {
            await this.chartExport.exportMultipleChartsAsPDF(this.state.selectedCharts);
            this.showNotification('Selected charts exported as PDF report', 'success');
        } catch (error) {
            this.showNotification('Failed to export charts: ' + error.message, 'danger');
        } finally {
            this.state.exporting = false;
        }
    }
}
```

## 2. Documentation

### 2.1 User Documentation

Create comprehensive user documentation:

```markdown
# Warranty Dashboard User Guide

## Overview

The Warranty Dashboard provides comprehensive analytics and insights into your warranty management system. It features interactive charts, real-time data updates, and powerful filtering capabilities.

## Dashboard Sections

### 1. Key Performance Indicators (KPIs)

The top section displays key metrics:
- **Total Warranties**: Total number of warranty cards in the system
- **Active Warranties**: Currently valid warranties
- **Expired Warranties**: Warranties that have passed their end date
- **Claimed Warranties**: Warranties with at least one claim

Each KPI card includes:
- Current count and percentage
- Progress bar showing proportion
- Click-to-view functionality for detailed records

### 2. Overview Charts

#### Warranty Status Distribution
- **Type**: Pie Chart
- **Purpose**: Shows the breakdown of warranty statuses
- **Interaction**: Click on any segment to view warranties with that status

#### Claims Trend Analysis
- **Type**: Line Chart
- **Purpose**: Displays claim trends over time
- **Features**: 
  - Multiple datasets for warranty vs out-of-warranty claims
  - Hover tooltips with detailed information
  - Click on data points for period-specific claims

#### Monthly Comparison
- **Type**: Bar Chart
- **Purpose**: Compares new warranties vs claims by month
- **Features**: Side-by-side comparison for easy analysis

### 3. Product & Customer Analytics

#### Top Products
- **Type**: Horizontal Bar Chart
- **Purpose**: Shows products with most warranties and claims
- **Interaction**: Click on product to view all related warranties

#### Top Customers
- **Type**: Horizontal Bar Chart
- **Purpose**: Displays customers with most warranties
- **Interaction**: Click on customer to view their warranty portfolio

### 4. Claims Analytics

#### Claim Types Analysis
- **Type**: Stacked Area Chart
- **Purpose**: Shows claim type distribution over time
- **Categories**: Repair, Replacement, Refund

#### Warranty Expiry Forecast
- **Type**: Bar Chart
- **Purpose**: Predicts warranty expirations for upcoming months
- **Use Case**: Proactive customer communication and inventory planning

## Interactive Features

### 1. Drill-Down Functionality

All charts support drill-down functionality:
- **Click** on any chart element to view detailed records
- **Right-click** for additional options
- **Hover** for detailed tooltips

### 2. Filtering System

The dashboard includes comprehensive filtering:

#### Date Range Filters
- Preset options: Last 7 days, 30 days, 3 months, 6 months, Year to date
- Custom date range selection
- Quarter to date and Month to date options

#### Product Filters
- Multi-select product filtering
- Search functionality for large product catalogs
- "All Products" option for overview

#### Customer Filters
- Multi-select customer filtering
- Search by customer name or code
- Filter by customer categories

#### Status Filters
- Warranty status selection (Active, Expired, Draft, Cancelled)
- Claim type filtering (Repair, Replacement, Refund)

### 3. Chart Interactions

#### Zoom and Pan
- **Mouse wheel**: Zoom in/out on time-based charts
- **Click and drag**: Pan across chart data
- **Reset zoom**: Double-click to reset view

#### Data Highlighting
- **Hover**: Highlight data points across all charts
- **Click**: Lock highlight for comparison
- **Escape**: Clear all highlights

## Export Functionality

### 1. Individual Chart Export

Each chart supports multiple export formats:
- **PNG**: High-quality image for presentations
- **JPG**: Compressed image for email/web use
- **PDF**: Vector format for reports
- **CSV**: Raw data for Excel analysis

### 2. Batch Export

Export all charts as a comprehensive PDF report:
- Includes all charts with titles
- Professional formatting
- Suitable for management reports

### 3. Data Export

Export chart data in various formats:
- **CSV**: For spreadsheet analysis
- **JSON**: For integration with other systems
- **Excel**: Direct Excel format (with additional library)

## Performance Tips

### 1. Optimize Loading
- Use date range filters to limit data
- Select specific products/customers for focused analysis
- Close unused browser tabs to improve performance

### 2. Browser Compatibility
- Chrome/Edge: Best performance
- Firefox: Good compatibility
- Safari: Supported with some limitations

### 3. Mobile Usage
- Charts are responsive and work on tablets
- Limited functionality on mobile phones
- Use landscape orientation for better viewing

## Troubleshooting

### Common Issues

#### Charts Not Loading
1. Check internet connection
2. Refresh the page
3. Clear browser cache
4. Try a different browser

#### Export Not Working
1. Disable popup blockers
2. Check browser download settings
3. Ensure sufficient disk space
4. Try a different export format

#### Slow Performance
1. Reduce date range
2. Apply specific filters
3. Close other browser tabs
4. Restart browser

### Error Messages

#### "Chart data not available"
- Data is being updated
- Try refreshing in a few moments
- Check if filters are too restrictive

#### "Export failed"
- Check browser permissions
- Try a different format
- Ensure stable internet connection

## Keyboard Shortcuts

- **Ctrl + R**: Refresh dashboard
- **Ctrl + E**: Export current chart
- **Ctrl + F**: Focus on filter search
- **Escape**: Clear selections and highlights
- **F11**: Fullscreen mode

## Support

For additional support:
1. Check the system status page
2. Contact your system administrator
3. Review the knowledge base articles
4. Submit a support ticket with screenshots

## Updates and Features

The dashboard is regularly updated with:
- New chart types based on user feedback
- Performance improvements
- Additional export options
- Enhanced filtering capabilities

Check the release notes for detailed information about updates.
```

### 2.2 Developer Documentation

```markdown
# Warranty Dashboard Developer Guide

## Architecture Overview

The dashboard consists of several key components:

### Backend Components

1. **WarrantyDashboardCache Model**
   - Stores pre-calculated chart data
   - Handles data aggregation and caching
   - Provides efficient data retrieval

2. **WarrantyDashboard Model**
   - Transient model for dashboard display
   - Links to cache data
   - Handles user interactions

### Frontend Components

1. **Chart Components**
   - Reusable chart widgets
   - Interactive features
   - Export functionality

2. **Filter Components**
   - Dynamic filtering system
   - Real-time updates
   - Preset configurations

## Data Flow

1. **Cache Update Process**
   ```
   Cron Job → Cache Model → SQL Queries → JSON Data → Frontend Charts
   ```

2. **Real-time Updates**
   ```
   User Action → Model Trigger → Cache Update → Frontend Refresh
   ```

3. **Filter Application**
   ```
   Filter Selection → Context Update → Data Refresh → Chart Update
   ```

## Chart Data Structure

All charts use a consistent JSON structure:

```json
{
    "type": "pie|line|bar|area",
    "data": {
        "labels": ["Label1", "Label2"],
        "datasets": [{
            "label": "Dataset Name",
            "data": [value1, value2],
            "backgroundColor": ["#color1", "#color2"],
            "borderColor": ["#color1", "#color2"],
            "borderWidth": 1
        }]
    },
    "options": {
        "responsive": true,
        "plugins": {
            "legend": {"position": "top"},
            "tooltip": {"enabled": true}
        }
    }
}
```

## Adding New Charts

### Backend Steps

1. Add chart data field to cache model
2. Implement data preparation method
3. Update cache refresh process
4. Add chart field to dashboard model

### Frontend Steps

1. Create chart component (if needed)
2. Add chart to dashboard view
3. Implement drill-down logic
4. Add export support

### Example: Adding a New Chart

```python
# Backend: Add to cache model
def _prepare_new_chart(self):
    self._cr.execute("SELECT ...")
    results = self._cr.fetchall()
    
    chart_data = {
        'type': 'bar',
        'data': {
            'labels': [r[0] for r in results],
            'datasets': [{
                'label': 'New Metric',
                'data': [r[1] for r in results],
                'backgroundColor': '#007bff'
            }]
        }
    }
    
    self.new_chart = json.dumps(chart_data)
```

```javascript
// Frontend: Add to dashboard
const newChart = new Chart(ctx, {
    type: 'bar',
    data: chartData.data,
    options: chartData.options
});
```

## Performance Optimization

### Database Optimization

1. Use indexed fields in queries
2. Limit result sets with LIMIT clauses
3. Aggregate data at database level
4. Cache frequently accessed data

### Frontend Optimization

1. Implement lazy loading for charts
2. Use debounced filter updates
3. Optimize chart rendering
4. Minimize DOM manipulations

### Caching Strategy

1. Cache chart data for 15 minutes
2. Use browser storage for static data
3. Implement incremental updates
4. Preload commonly used data

## Testing

### Unit Tests

```python
# Test chart data preparation
def test_warranty_status_chart(self):
    cache = self.env['warranty.dashboard.cache'].create({})
    cache._prepare_warranty_status_chart()
    
    chart_data = json.loads(cache.warranty_status_chart)
    self.assertEqual(chart_data['type'], 'pie')
    self.assertIn('data', chart_data)
```

### Integration Tests

```javascript
// Test chart rendering
test('chart renders correctly', async () => {
    const chart = mountChart('warranty_status_chart', mockData);
    expect(chart.canvas).toBeInTheDocument();
    expect(chart.data.datasets).toHaveLength(1);
});
```

### Performance Tests

```python
# Test cache update performance
def test_cache_update_performance(self):
    start_time = time.time()
    cache._update_all_metrics()
    duration = time.time() - start_time
    
    self.assertLess(duration, 5.0, "Cache update should complete within 5 seconds")
```

## Security Considerations

1. **Data Access Control**
   - Respect Odoo record rules
   - Implement user-based filtering
   - Validate input parameters

2. **SQL Injection Prevention**
   - Use parameterized queries
   - Validate user inputs
   - Escape dynamic values

3. **XSS Prevention**
   - Sanitize user inputs
   - Escape output values
   - Use secure templating

## Deployment

### Production Deployment

1. **Database Migration**
   ```sql
   -- Add new fields
   ALTER TABLE warranty_dashboard_cache ADD COLUMN new_chart TEXT;
   ```

2. **Asset Compilation**
   ```bash
   # Compile SCSS
   sass static/src/scss/dashboard_charts.scss:static/src/scss/dashboard_charts.css
   
   # Minify JavaScript
   uglifyjs static/src/js/dashboard_charts.js -o static/src/js/dashboard_charts.min.js
   ```

3. **Cache Initialization**
   ```python
   # Initialize cache data
   env['warranty.dashboard.cache']._cron_update_dashboard_cache()
   ```

### Monitoring

1. **Performance Metrics**
   - Chart render time
   - Cache update duration
   - Database query performance

2. **Error Tracking**
   - Chart rendering errors
   - Data preparation failures
   - Export functionality issues

3. **Usage Analytics**
   - Most used charts
   - Common filter combinations
   - Export frequency

## Troubleshooting

### Common Development Issues

1. **Chart Not Rendering**
   - Check Chart.js library loading
   - Verify data structure
   - Inspect console errors

2. **Data Not Updating**
   - Check cache refresh process
   - Verify trigger mechanisms
   - Review cron job configuration

3. **Performance Issues**
   - Profile SQL queries
   - Check chart rendering optimization
   - Monitor memory usage

### Debug Tools

1. **Browser Developer Tools**
   - Network tab for API calls
   - Console for JavaScript errors
   - Performance tab for rendering analysis

2. **Odoo Debug Mode**
   - Enable debug mode
   - Check view definitions
   - Review data access logs

## Best Practices

1. **Code Organization**
   - Separate concerns (data, presentation, interaction)
   - Use consistent naming conventions
   - Document complex logic

2. **Error Handling**
   - Provide meaningful error messages
   - Implement graceful degradation
   - Log errors for debugging

3. **User Experience**
   - Provide loading indicators
   - Implement responsive design
   - Ensure accessibility compliance

4. **Maintainability**
   - Write modular code
   - Use version control
   - Implement automated testing
```

This comprehensive implementation provides:
- Complete export functionality for all chart types
- Multiple export formats (PNG, JPG, PDF, CSV)
- Batch export capabilities
- Comprehensive user documentation
- Detailed developer documentation
- Performance optimization guidelines
- Security considerations
- Troubleshooting guides
- Best practices for maintenance

The documentation ensures that both end users and developers can effectively use and extend the dashboard functionality.