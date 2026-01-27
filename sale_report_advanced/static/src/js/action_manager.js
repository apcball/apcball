/** @odoo-module **/
import { registry } from "@web/core/registry";
import { blockUI, unblockUI } from "@web/core/ui/block_ui";
import { download } from "@web/core/network/download";

/**
 * XLSX Handler
 * This handler is responsible for generating XLSX reports.
 * It sends a request to the server to generate the report in XLSX format and
 * downloads the generated file.
 * @param {Object} action - The action object containing the report details.
 * @returns {Promise} - A promise that resolves when the report generation is complete.
 */
registry.category("ir.actions.report.handlers").add("xlsx", async function (action) {
    if (action.report_type === 'xlsx') {
        blockUI();
        try {
            await download({
                url: '/xlsx_reports',
                data: action.data,
            });
        } catch (error) {
            console.error('XLSX Report Generation Error:', error);
            throw error;
        } finally {
            unblockUI();
        }
        return true;
    }
    return false;
});
