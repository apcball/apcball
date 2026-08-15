/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const LINE_SERVICE_MODEL = "buz.helpdesk.line.service";

export class HelpdeskLineSettings extends Component {
    static template = "buz_it_helpdesk.HelpdeskLineSettings";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            saving: false,
            testing: false,
            companies: [],
            companyId: null,
            companyName: "",
            token: "",
            tokenConfigured: false,
            groupId: "",
            result: null,
            error: "",
        });
        onWillStart(() => this.loadSettings());
    }

    errorMessage(error) {
        return error?.data?.message || error?.message || "Unable to process LINE settings.";
    }

    applySettings(data) {
        this.state.companies = data.companies || this.state.companies;
        this.state.companyId = data.company_id;
        this.state.companyName = data.company_name || "";
        this.state.groupId = data.group_id || "";
        this.state.tokenConfigured = Boolean(data.token_configured);
        this.state.token = "";
    }

    async loadSettings(companyId = null) {
        this.state.loading = true;
        this.state.error = "";
        this.state.result = null;
        try {
            const args = companyId ? [companyId] : [];
            const data = await this.orm.call(
                LINE_SERVICE_MODEL,
                "get_line_settings",
                args,
            );
            this.applySettings(data);
        } catch (error) {
            this.state.error = this.errorMessage(error);
        } finally {
            this.state.loading = false;
        }
    }

    async onCompanyChange(event) {
        await this.loadSettings(Number(event.target.value));
    }

    onTokenInput(event) {
        this.state.token = event.target.value;
        this.state.result = null;
    }

    onGroupInput(event) {
        this.state.groupId = event.target.value;
        this.state.result = null;
    }

    async save() {
        if (this.state.saving || this.state.testing) {
            return;
        }
        this.state.saving = true;
        this.state.error = "";
        this.state.result = null;
        try {
            const data = await this.orm.call(
                LINE_SERVICE_MODEL,
                "save_line_settings",
                [this.state.companyId, this.state.token, this.state.groupId],
            );
            this.applySettings(data);
            const message = data.group_id
                ? `LINE settings saved for ${data.company_name}.`
                : `LINE notifications disabled for ${data.company_name}.`;
            this.notification.add(message, { type: "success" });
        } catch (error) {
            const message = this.errorMessage(error);
            this.state.error = message;
            this.notification.add(message, { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    async saveAndTest() {
        if (this.state.saving || this.state.testing) {
            return;
        }
        this.state.testing = true;
        this.state.error = "";
        this.state.result = null;
        try {
            const data = await this.orm.call(
                LINE_SERVICE_MODEL,
                "save_and_test_line_settings",
                [this.state.companyId, this.state.token, this.state.groupId],
            );
            this.applySettings(data);
            this.state.result = {
                botName: data.bot_name,
                botBasicId: data.bot_basic_id,
                groupName: data.group_name,
                groupId: data.group_id,
                companyName: data.company_name,
            };
            this.notification.add(
                `LINE test message sent to ${data.group_name || data.group_id}.`,
                { type: "success" },
            );
        } catch (error) {
            const message = this.errorMessage(error);
            this.state.error = message;
            this.notification.add(message, { type: "danger", sticky: true });
        } finally {
            this.state.testing = false;
        }
    }
}

registry.category("actions").add(
    "buz_it_helpdesk.line_settings",
    HelpdeskLineSettings,
);
