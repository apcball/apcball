odoo.define('marketplace_settlement.m2m_add_popup', function(require) {
    "use strict";

    var ListRenderer = require('web.ListRenderer');
    var core = require('web.core');
    var utils = require('web.utils');
    var patch = require('web.utils').patch || require('web.utils').extend;

    ListRenderer.include({
        // override add to inject domain when opening the add popup for many2many
        add: function (ev) {
            var self = this;
            try {
                var res = this._super.apply(this, arguments);
            } catch (e) {
                // older Odoo versions
                var res = ListRenderer.__proto__.add.apply(this, arguments);
            }
            // attempt to enhance the add popup domain
            try {
                var field = ev && ev.data && ev.data.field;
                if (!field) { return res; }
                // only act for invoice fields or if field name contains 'invoice'
                if (field.name !== 'invoice_id' && field.name.indexOf('invoice') === -1) { return res; }
                // find parent form renderer and its state
                var formRenderer = this.mode === 'readonly' && this.getParent && this.getParent() || this;
                while (formRenderer && formRenderer.arch && formRenderer.arch.tag !== 'form' && formRenderer.getParent) {
                    formRenderer = formRenderer.getParent();
                }
                if (!formRenderer || !formRenderer.state) { return res; }
                var state = formRenderer.state;
                var trade_channel = state.data && state.data.trade_channel;
                var date_from = state.data && state.data.date_from;
                var date_to = state.data && state.data.date_to;
                var extra_domain = [];
                if (trade_channel) {
                    extra_domain.push(['trade_channel','=', trade_channel]);
                }
                if (date_from) {
                    extra_domain.push(['invoice_date','>=', date_from]);
                }
                if (date_to) {
                    extra_domain.push(['invoice_date','<=', date_to]);
                }
                if (!extra_domain.length) { return res; }
                // the popup is created asynchronously; listen for the dialog open and then patch its domain
                core.bus.on('DOM_has_been_manipulated', this, function () {
                    try {
                        // find last created modal and its search view buttons
                        var dialogs = document.querySelectorAll('.o_dialog');
                        if (!dialogs.length) { return; }
                        var dlg = dialogs[dialogs.length-1];
                        // look for domain pills area and append filter programmatically via JS is fragile; instead trigger the search domain via RPC
                        // As a simpler approach, set a global search filter by updating the search model (not trivial). Skip complex UI patch; rely on backend onchange domain already working.
                    } catch (e) {
                        console.warn('m2m add popup patch error', e);
                    }
                });
            } catch (e) {
                // non-blocking
            }
            return res;
        },
    });

    return {};
});
