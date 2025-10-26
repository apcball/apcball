/**
 * Simple Chart.js implementation for Odoo 17
 * This provides basic chart functionality without external dependencies
 */

// Simple Chart constructor
window.Chart = function(ctx, config) {
    this.ctx = ctx;
    this.config = config || {};
    this.data = this.config.data || {};
    this.options = this.config.options || {};
    this.type = this.config.type || 'bar';
};

// Chart prototype methods
Chart.prototype.render = function() {
    const { labels, datasets } = this.data;
    const chartWidth = this.ctx.canvas.width;
    const chartHeight = this.ctx.canvas.height;
    const padding = 40;
    
    // Clear canvas
    this.ctx.clearRect(0, 0, chartWidth, chartHeight);
    
    // Set default styles
    this.ctx.font = '12px Arial';
    this.ctx.textAlign = 'center';
    this.ctx.textBaseline = 'middle';
    
    switch (this.type) {
        case 'pie':
            this.renderPieChart(labels, datasets, chartWidth, chartHeight, padding);
            break;
        case 'line':
            this.renderLineChart(labels, datasets, chartWidth, chartHeight, padding);
            break;
        case 'bar':
            this.renderBarChart(labels, datasets, chartWidth, chartHeight, padding);
            break;
        default:
            console.warn('Chart type not supported:', this.type);
    }
};

Chart.prototype.renderPieChart = function(labels, datasets, width, height, padding) {
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) / 2 - padding;
    
    let currentAngle = -Math.PI / 2;
    const total = datasets[0].data.reduce((sum, value) => sum + value, 0);
    
    const colors = [
        '#007bff', '#28a745', '#dc3545', '#ffc107', '#17a2b8',
        '#6f42c1', '#e83e8c', '#20c997', '#fd7e14'
    ];
    
    datasets[0].data.forEach((value, index) => {
        const sliceAngle = (value / total) * 2 * Math.PI;
        const endAngle = currentAngle + sliceAngle;
        
        // Draw pie slice
        this.ctx.beginPath();
        this.ctx.moveTo(centerX, centerY);
        this.ctx.arc(centerX, centerY, radius, currentAngle, endAngle);
        this.ctx.closePath();
        
        this.ctx.fillStyle = colors[index % colors.length];
        this.ctx.fill();
        
        // Draw border
        this.ctx.strokeStyle = '#ffffff';
        this.ctx.lineWidth = 2;
        this.ctx.stroke();
        
        currentAngle = endAngle;
    });
};

Chart.prototype.renderLineChart = function(labels, datasets, width, height, padding) {
    const chartArea = {
        left: padding,
        top: padding,
        right: width - padding,
        bottom: height - padding
    };
    
    const chartWidth = chartArea.right - chartArea.left;
    const chartHeight = chartArea.bottom - chartArea.top;
    
    // Find data ranges
    let minY = Infinity, maxY = -Infinity;
    datasets.forEach(dataset => {
        dataset.data.forEach(value => {
            minY = Math.min(minY, value);
            maxY = Math.max(maxY, value);
        });
    });
    
    const yRange = maxY - minY;
    const xStep = chartWidth / (labels.length - 1);
    
    // Draw axes
    this.ctx.strokeStyle = '#e0e0e0';
    this.ctx.lineWidth = 1;
    this.ctx.beginPath();
    this.ctx.moveTo(chartArea.left, chartArea.top);
    this.ctx.lineTo(chartArea.left, chartArea.bottom);
    this.ctx.lineTo(chartArea.right, chartArea.bottom);
    this.ctx.stroke();
    
    // Draw grid lines
    this.ctx.strokeStyle = '#f0f0f0';
    this.ctx.lineWidth = 0.5;
    for (let i = 0; i <= 5; i++) {
        const y = chartArea.top + (chartHeight / 5) * i;
        this.ctx.beginPath();
        this.ctx.moveTo(chartArea.left, y);
        this.ctx.lineTo(chartArea.right, y);
        this.ctx.stroke();
    }
    
    // Draw datasets
    const colors = ['#007bff', '#28a745', '#dc3545', '#ffc107'];
    
    datasets.forEach((dataset, datasetIndex) => {
        const color = colors[datasetIndex % colors.length];
        
        this.ctx.strokeStyle = color;
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();
        
        dataset.data.forEach((value, index) => {
            const x = chartArea.left + (index * xStep);
            const y = chartArea.bottom - ((value - minY) / yRange) * chartHeight;
            
            if (index === 0) {
                this.ctx.moveTo(x, y);
            } else {
                this.ctx.lineTo(x, y);
            }
        });
        
        this.ctx.stroke();
    });
    
    // Draw labels
    this.ctx.fillStyle = '#495057';
    labels.forEach((label, index) => {
        const x = chartArea.left + (index * xStep);
        this.ctx.fillText(label, x, chartArea.bottom + 5);
    });
};

Chart.prototype.renderBarChart = function(labels, datasets, width, height, padding) {
    const chartArea = {
        left: padding,
        top: padding,
        right: width - padding,
        bottom: height - padding
    };
    
    const chartWidth = chartArea.right - chartArea.left;
    const chartHeight = chartArea.bottom - chartArea.top;
    const barWidth = chartWidth / (labels.length * datasets.length + 1);
    const groupWidth = barWidth * datasets.length;
    const groupSpacing = chartWidth / labels.length;
    
    // Find data ranges
    let maxY = -Infinity;
    datasets.forEach(dataset => {
        dataset.data.forEach(value => {
            maxY = Math.max(maxY, value);
        });
    });
    
    const yRange = maxY;
    
    // Draw axes
    this.ctx.strokeStyle = '#e0e0e0';
    this.ctx.lineWidth = 1;
    this.ctx.beginPath();
    this.ctx.moveTo(chartArea.left, chartArea.top);
    this.ctx.lineTo(chartArea.left, chartArea.bottom);
    this.ctx.lineTo(chartArea.right, chartArea.bottom);
    this.ctx.stroke();
    
    // Draw datasets
    const colors = ['#007bff', '#28a745', '#dc3545', '#ffc107'];
    
    labels.forEach((label, labelIndex) => {
        const groupX = chartArea.left + (labelIndex * groupSpacing) + padding;
        
        datasets.forEach((dataset, datasetIndex) => {
            const value = dataset.data[labelIndex];
            const barHeight = (value / yRange) * chartHeight;
            const barX = groupX + (datasetIndex * barWidth);
            
            this.ctx.fillStyle = colors[datasetIndex % colors.length];
            this.ctx.fillRect(barX, chartArea.bottom - barHeight, barWidth, barHeight);
        });
    });
    
    // Draw labels
    this.ctx.fillStyle = '#495057';
    this.ctx.textAlign = 'center';
    labels.forEach((label, index) => {
        const x = chartArea.left + (index * groupSpacing) + (groupWidth / 2);
        this.ctx.fillText(label, x, chartArea.bottom + 5);
    });
};

Chart.prototype.update = function() {
    this.render();
};

Chart.prototype.destroy = function() {
    // Clean up if needed
    this.ctx = null;
};

Chart.prototype.toBase64Image = function() {
    return this.ctx.canvas.toDataURL('image/png');
};