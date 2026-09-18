/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
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
                botPictureUrl: data.bot_picture_url,
                addFriendUrl: data.add_friend_url,
                groupName: data.group_name,
                groupId: data.group_id,
                companyName: data.company_name,
            };
            const testMessage = data.tested_company_count > 1
                ? "LINE test messages sent to " + data.tested_company_count + " company destinations."
                : "LINE test message sent to " + (data.group_name || data.group_id) + ".";
            this.notification.add(testMessage, { type: "success" });
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
        this.action = useService("action");
        this.state = useState({
            softReminder: Boolean(this.props.action?.context?.soft_line_reminder),
            loading: true, connected: false, masked: "", code: "",
            expiresAt: 0, expiresAtText: "", remaining: 0, error: "", botName: "",
            basicId: "", pictureUrl: "", addFriendUrl: "", qrDataUrl: "", qrError: "",
        });
        this.pollTimer = null;
        this.expiryTimer = null;
        onWillStart(() => this.load());
        onWillUnmount(() => this.clearTimers());
    }

    errorMessage(error) {
        return error?.data?.message || error?.message || "Unable to process LINE connection.";
    }

    clearTimers() {
        clearInterval(this.pollTimer);
        clearInterval(this.expiryTimer);
    }

    async load() {
        try {
            const data = await this.orm.call(LINE_SERVICE_MODEL, "get_line_connection_status", []);
            this.applyStatus(data);
        } catch (error) {
            this.state.error = this.errorMessage(error);
        } finally {
            this.state.loading = false;
        }
    }

    applyStatus(data) {
        this.state.connected = data.connected;
        this.state.masked = data.line_user_masked || "";
        this.state.botName = data.display_name || "";
        this.state.basicId = data.basic_id || "";
        this.state.pictureUrl = data.picture_url || "";
        this.state.addFriendUrl = data.add_friend_url || "";
        this.refreshQr();
        if (data.connected) {
            this.state.code = "";
            this.clearTimers();
        }
    }

    refreshQr() {
        this.state.qrError = "";
        if (!this.state.addFriendUrl) {
            this.state.qrDataUrl = "";
            return;
        }
        try {
            if (typeof window.qrcode !== "function") {
                throw new Error("QR code generator is unavailable in the backend assets.");
            }
            const qr = window.qrcode(0, "M");
            qr.addData(this.state.addFriendUrl);
            qr.make();
            this.state.qrDataUrl = qr.createDataURL(6, 2);
        } catch (error) {
            this.state.qrDataUrl = "";
            this.state.qrError = "สร้าง QR Code ไม่สำเร็จ กรุณาโหลดหน้าใหม่หรือติดต่อ Helpdesk Manager";
            console.error("Unable to generate LINE Official Account QR code.", error);
        }
    }

    async createCode() {
        this.state.error = "";
        try {
            const data = await this.orm.call(LINE_SERVICE_MODEL, "create_line_connection_code", []);
            this.state.code = data.code;
            this.state.expiresAt = Date.now() + data.expires_in * 1000;
            this.state.expiresAtText = new Date(this.state.expiresAt).toLocaleTimeString();
            this.state.remaining = data.expires_in;
            this.startPolling();
        } catch (error) {
            this.state.error = this.errorMessage(error);
        }
    }

    startPolling() {
        this.clearTimers();
        this.pollTimer = setInterval(() => this.load(), 2000);
        this.expiryTimer = setInterval(() => {
            this.state.remaining = Math.max(0, Math.ceil((this.state.expiresAt - Date.now()) / 1000));
            if (!this.state.remaining) {
                this.state.code = "";
                this.clearTimers();
            }
        }, 500);
    }

    async copyCode() {
        try {
            await navigator.clipboard.writeText(this.state.code);
            this.notification.add("คัดลอกรหัสเชื่อมต่อแล้ว", {type: "success"});
        } catch {
            this.state.error = "คัดลอกรหัสไม่สำเร็จ กรุณาเลือกและคัดลอกรหัสด้วยตนเอง";
        }
    }

    async close() {
        await this.action.doAction({type: "ir.actions.act_window_close"});
    }

    async remindLater() {
        await this.close();
    }

    async cancel() {
        if (!window.confirm("ต้องการยกเลิกการเชื่อมต่อบัญชี LINE นี้หรือไม่?")) return;
        try {
            const data = await this.orm.call(LINE_SERVICE_MODEL, "cancel_line_connection", []);
            this.applyStatus(data);
            this.notification.add("ยกเลิกการเชื่อมต่อบัญชี LINE แล้ว", {type: "success"});
        } catch (error) {
            this.state.error = this.errorMessage(error);
        }
    }
}

registry.category("actions").add(
    "buz_it_helpdesk.line_settings",
    HelpdeskLineSettings,
);
registry.category("actions").add("buz_it_helpdesk.line_connection", HelpdeskLineConnection);
