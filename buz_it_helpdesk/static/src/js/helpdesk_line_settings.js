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
            secret: "",
            secretConfigured: false,
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
        this.state.secretConfigured = Boolean(data.secret_configured);
        this.state.token = "";
        this.state.secret = "";
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

    onSecretInput(event) {
        this.state.secret = event.target.value;
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
                [this.state.companyId, this.state.token, this.state.groupId, this.state.secret],
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
                [this.state.companyId, this.state.token, this.state.groupId, this.state.secret],
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

export class HelpdeskLineConnection extends Component {
    static template = "buz_it_helpdesk.HelpdeskLineConnection";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({loading: true, connected: false, masked: "", code: "", expires: 0, error: ""});
        onWillStart(() => this.load());
    }

    errorMessage(error) {
        return error?.data?.message || error?.message || "Unable to process LINE connection.";
    }

    async load() {
        try {
            const data = await this.orm.call(LINE_SERVICE_MODEL, "get_line_connection_status", []);
            this.state.connected = data.connected;
            this.state.masked = data.line_user_masked || "";
        } catch (error) { this.state.error = this.errorMessage(error); }
        finally { this.state.loading = false; }
    }

    async createCode() {
        try {
            const data = await this.orm.call(LINE_SERVICE_MODEL, "create_line_connection_code", []);
            this.state.code = data.code;
            this.state.expires = data.expires_in;
        } catch (error) { this.state.error = this.errorMessage(error); }
    }

    async cancel() {
        if (!window.confirm("Disconnect this LINE account from Odoo?")) return;
        try {
            await this.orm.call(LINE_SERVICE_MODEL, "cancel_line_connection", []);
            this.state.connected = false; this.state.masked = ""; this.state.code = "";
            this.notification.add("LINE account disconnected.", {type: "success"});
        } catch (error) { this.state.error = this.errorMessage(error); }
    }
}

registry.category("actions").add(
    "buz_it_helpdesk.line_settings",
    HelpdeskLineSettings,
);
registry.category("actions").add("buz_it_helpdesk.line_connection", HelpdeskLineConnection);
