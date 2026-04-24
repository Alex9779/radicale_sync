// Copyright (c) 2026, Frappe Community and contributors
// For license information, please see license.txt

frappe.ui.form.on("Radicale Contacts", {
	refresh(frm) {
		if (!frm.doc.enable) {
			frm.dashboard.set_headline_alert(
				__("This account is disabled. Enable it to start syncing contacts.")
			);
		}

		if (!frm.is_new()) {
			frm.add_custom_button(__("Test Connection"), function () {
				frappe.show_alert({ indicator: "blue", message: __("Testing connection...") });
				frappe
					.call({
						method: "radicale_sync.radicale_sync.doctype.radicale_contacts.radicale_contacts.test_connection",
						args: { radicale_contact: frm.doc.name },
					})
					.then((r) => {
						const res = r.message;
						frappe.msgprint({
							title: res.success ? __("Connection Successful") : __("Connection Failed"),
							indicator: res.success ? "green" : "red",
							message: res.message,
						});
					});
			});

			if (frm.doc.enable) {
				frm.add_custom_button(__("Sync Contacts"), function () {
					frappe.show_alert({ indicator: "green", message: __("Syncing...") });
					frappe
						.call({
							method: "radicale_sync.radicale_sync.doctype.radicale_contacts.radicale_contacts.sync",
							args: { radicale_contact: frm.doc.name },
						})
						.then((r) => {
							frappe.msgprint(
								Array.isArray(r.message) ? r.message.join("<br>") : r.message
							);
						});
				});
			}
		}
	},
});
