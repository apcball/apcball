/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";

const { onMounted, onWillUnmount } = owl;

export class WarrantyDashboardController extends FormController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        this.refreshInterval = null;
        this.countdownInterval = null;
        this.refreshIntervalTime = 5 * 60 * 1000;
        this.checkIntervalTime = 30 * 1000;
        
        onMounted(() => {
            this.startAutoRefresh();
        });
        
        onWillUnmount(() => {
            this.stopAutoRefresh();
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
            
            this.startCountdown();
            
            this.notification.add(
                "Dashboard data refreshed",
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
}

export const warrantyDashboardView = {
    ...formView,
    Controller: WarrantyDashboardController,
};

registry.category("views").add("warranty_dashboard_form", warrantyDashboardView);
