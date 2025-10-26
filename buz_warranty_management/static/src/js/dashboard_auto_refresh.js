/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";

export class WarrantyDashboardController extends FormController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");
        
        this.refreshInterval = null;
        this.countdownInterval = null;
        this.refreshIntervalTime = 5 * 60 * 1000;
        this.checkIntervalTime = 30 * 1000;
        
        // Chart state
        this.charts = useState({
            status: null,
            trend: null,
            comparison: null,
            products: null,
            customers: null,
            types: null,
            expiry: null
        });
        
        onMounted(() => {
            this.startAutoRefresh();
            this.initializeCharts();
        });
        
        onWillUnmount(() => {
            this.stopAutoRefresh();
            this.destroyCharts();
        });
    }
    
    initializeCharts() {
        // Setup chart containers
        this.setupChartContainers();
        
        // Load initial chart data
        this.loadAllChartData();
    }
    
    setupChartContainers() {
        // Setup chart containers with proper dimensions
        const chartContainers = document.querySelectorAll('.chart-container');
        chartContainers.forEach(container => {
            container.style.position = 'relative';
            container.style.height = '300px';
        });
    }
    
    async loadAllChartData() {
        try {
            const record = this.model.root.data;
            
            // Load chart data from cache
            this.charts.status = record.warranty_status_chart;
            this.charts.trend = record.claims_trend_chart;
            this.charts.comparison = record.monthly_comparison_chart;
            this.charts.products = record.top_products_chart;
            this.charts.customers = record.top_customers_chart;
            this.charts.types = record.claim_types_chart;
            this.charts.expiry = record.warranty_expiry_chart;
            
            // Render charts
            this.renderAllCharts();
            
        } catch (error) {
            console.error("Error loading chart data:", error);
            this.notification.add(
                "Failed to load chart data",
                { type: "danger" }
            );
        }
    }
    
    renderAllCharts() {
        // This will be handled by OWL components
        // The components will automatically re-render when state changes
    }
    
    destroyCharts() {
        // Clean up chart instances
        Object.values(this.charts).forEach(chart => {
            if (chart && chart.destroy) {
                chart.destroy();
            }
        });
    }
    
    startAutoRefresh() {
        this.refreshInterval = setInterval(() => {
            this.checkCacheStatus();
        }, this.checkIntervalTime);
        
        this.startCountdown();
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
        if (this.countdownInterval) {
            clearInterval(this.countdownInterval);
            this.countdownInterval = null;
        }
    }
    
    async checkCacheStatus() {
        if (!this.model.root.resId) {
            return;
        }
        
        try {
            const record = this.model.root.data;
            const cacheStatus = record.cache_status;
            const cacheValidUntil = record.cache_valid_until;
            
            if (cacheStatus === 'expired' || 
                (cacheValidUntil && new Date(cacheValidUntil) < new Date())) {
                await this.autoRefresh();
            }
        } catch (error) {
            console.error("Error checking cache status:", error);
        }
    }
    
    startCountdown() {
        if (this.countdownInterval) {
            clearInterval(this.countdownInterval);
        }
        
        this.countdownInterval = setInterval(() => {
            this.updateCountdown();
        }, 1000);
    }
    
    updateCountdown() {
        if (!this.model.root.resId) {
            return;
        }
        
        try {
            const record = this.model.root.data;
            const cacheValidUntil = record.cache_valid_until;
            
            if (!cacheValidUntil) {
                return;
            }
            
            const now = new Date();
            const validUntil = new Date(cacheValidUntil);
            const diff = validUntil - now;
            
            const countdownEl = document.querySelector('.auto-refresh-countdown');
            if (!countdownEl) {
                return;
            }
            
            if (diff <= 0) {
                countdownEl.textContent = 'Expired';
                return;
            }
            
            const minutes = Math.floor(diff / 60000);
            const seconds = Math.floor((diff % 60000) / 1000);
            
            countdownEl.textContent = 
                minutes + ':' + (seconds < 10 ? '0' : '') + seconds;
        } catch (error) {
            console.error("Error updating countdown:", error);
        }
    }
    
    async autoRefresh() {
        try {
            await this.model.root.load();
            this.model.notify();
            
            // Reload chart data
            await this.loadAllChartData();
            
            this.startCountdown();
            
            this.notification.add(
                "Dashboard and charts refreshed",
                { type: "success" }
            );
        } catch (error) {
            console.error("Error auto-refreshing dashboard:", error);
            this.notification.add(
                "Failed to refresh dashboard: " + error.message,
                { type: "danger" }
            );
        }
    }
    
    // Chart interaction handlers
    onChartClick(chartType, data) {
        console.log(`Chart clicked: ${chartType}`, data);
        
        // Implement drill-down functionality
        switch (chartType) {
            case 'warranty_status_chart':
                this.drillDownWarrantyStatus(data);
                break;
            case 'top_products_chart':
                this.drillDownProducts(data);
                break;
            case 'top_customers_chart':
                this.drillDownCustomers(data);
                break;
            case 'claims_trend_chart':
                this.drillDownClaimsTrend(data);
                break;
            case 'claim_types_chart':
                this.drillDownClaimTypes(data);
                break;
            case 'warranty_expiry_chart':
                this.drillDownWarrantyExpiry(data);
                break;
            case 'monthly_comparison_chart':
                this.drillDownMonthlyComparison(data);
                break;
            default:
                console.log('No drill-down defined for', chartType);
        }
    }
    
    drillDownWarrantyStatus(data) {
        const statusMap = {
            'Active': 'active',
            'Expired': 'expired',
            'Draft': 'draft',
            'Cancelled': 'cancelled'
        };
        
        const status = statusMap[data.label];
        if (status) {
            this.actionService.doAction({
                type: 'ir.actions.act_window',
                res_model: 'warranty.card',
                view_mode: 'tree,form',
                domain: [['state', '=', status]],
                name: `${data.label} Warranties`
            });
        }
    }
    
    drillDownProducts(data) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.card',
            view_mode: 'tree,form',
            domain: [['product_id.product_tmpl_id.name', '=', data.label]],
            name: `Warranties for ${data.label}`
        });
    }
    
    drillDownCustomers(data) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.card',
            view_mode: 'tree,form',
            domain: [['partner_id.name', '=', data.label]],
            name: `Warranties for ${data.label}`
        });
    }
    
    drillDownClaimsTrend(data) {
        // Extract month from label and filter claims
        const monthLabel = data.label;
        // This would need more sophisticated date parsing
        console.log('Drill down to claims for:', monthLabel);
    }
    
    drillDownClaimTypes(data) {
        const monthLabel = data.label;
        const claimType = data.dataset.label;
        
        // Parse month and create domain
        const dateRange = this.parseMonthLabel(monthLabel);
        if (dateRange) {
            this.actionService.doAction({
                type: 'ir.actions.act_window',
                res_model: 'warranty.claim',
                view_mode: 'tree,form',
                domain: [
                    ['claim_date', '>=', dateRange.start],
                    ['claim_date', '<=', dateRange.end],
                    ['claim_type', '=', claimType.toLowerCase()]
                ],
                name: `${claimType} Claims for ${monthLabel}`
            });
        }
    }
    
    drillDownWarrantyExpiry(data) {
        const monthLabel = data.label;
        const dateRange = this.parseMonthLabel(monthLabel);
        if (dateRange) {
            this.actionService.doAction({
                type: 'ir.actions.act_window',
                res_model: 'warranty.card',
                view_mode: 'tree,form',
                domain: [
                    ['end_date', '>=', dateRange.start],
                    ['end_date', '<=', dateRange.end]
                ],
                name: `Warranties Expiring in ${monthLabel}`
            });
        }
    }
    
    drillDownMonthlyComparison(data) {
        const monthLabel = data.label;
        const datasetType = data.dataset.label;
        
        if (datasetType === 'New Warranties') {
            // Show warranties for this month
            const dateRange = this.parseMonthLabel(monthLabel);
            if (dateRange) {
                this.actionService.doAction({
                    type: 'ir.actions.act_window',
                    res_model: 'warranty.card',
                    view_mode: 'tree,form',
                    domain: [
                        ['create_date', '>=', dateRange.start],
                        ['create_date', '<=', dateRange.end]
                    ],
                    name: `Warranties created in ${monthLabel}`
                });
            }
        } else if (datasetType === 'Claims') {
            // Show claims for this month
            const dateRange = this.parseMonthLabel(monthLabel);
            if (dateRange) {
                this.actionService.doAction({
                    type: 'ir.actions.act_window',
                    res_model: 'warranty.claim',
                    view_mode: 'tree,form',
                    domain: [
                        ['claim_date', '>=', dateRange.start],
                        ['claim_date', '<=', dateRange.end]
                    ],
                    name: `Claims filed in ${monthLabel}`
                });
            }
        }
    }
    
    // Helper method to parse month labels
    parseMonthLabel(monthLabel) {
        // Parse labels like "Jan 2023", "February 2023", etc.
        const months = {
            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
        };
        
        const fullMonths = {
            'January': '01', 'February': '02', 'March': '03', 'April': '04',
            'May': '05', 'June': '06', 'July': '07', 'August': '08',
            'September': '09', 'October': '10', 'November': '11', 'December': '12'
        };
        
        const parts = monthLabel.split(' ');
        if (parts.length === 2) {
            const month = months[parts[0]] || fullMonths[parts[0]];
            const year = parts[1];
            
            if (month && year) {
                const startDate = `${year}-${month}-01`;
                const endDate = `${year}-${month}-31`; // Simplified, would need proper month end calculation
                return { start: startDate, end: endDate };
            }
        }
        
        return null;
    }
    
    // Export chart functionality
    exportChart(chartId, format = 'png') {
        const chart = this.getChartById(chartId);
        if (!chart) {
            this.notification.add(
                "Chart not found",
                { type: "warning" }
            );
            return;
        }
        
        try {
            if (format === 'png') {
                const url = chart.toBase64Image();
                const link = document.createElement('a');
                link.download = `${chartId}_chart.png`;
                link.href = url;
                link.click();
            } else if (format === 'pdf') {
                // This would require additional PDF library integration
                this.notification.add(
                    "PDF export not yet implemented",
                    { type: "info" }
                );
            }
            
            this.notification.add(
                `Chart exported as ${format.toUpperCase()}`,
                { type: "success" }
            );
        } catch (error) {
            this.notification.add(
                "Failed to export chart: " + error.message,
                { type: "danger" }
            );
        }
    }
    
    getChartById(chartId) {
        const canvas = document.querySelector(`#${chartId}`);
        return canvas ? SimpleChart.getChart(canvas) : null;
    }
}

export const warrantyDashboardView = {
    ...formView,
    Controller: WarrantyDashboardController,
};

registry.category("views").add("warranty_dashboard_form", warrantyDashboardView);
