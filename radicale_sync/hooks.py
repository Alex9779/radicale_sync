app_name = "radicale_sync"
app_title = "Radicale Sync"
app_publisher = "Frappe Community"
app_description = "Sync contacts and calendar events with a Radicale CardDAV/CalDAV server"
app_email = "support@example.com"
app_license = "mit"

# Required apps
required_apps = ["frappe"]

# Fixtures – installs Custom Fields on Contact and Event
fixtures = ["Custom Field"]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "radicale_sync",
# 		"logo": "/assets/radicale_sync/logo.png",
# 		"title": "Radicale Sync",
# 		"route": "/radicale_sync",
# 		"has_permission": "radicale_sync.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/radicale_sync/css/radicale_sync.css"
# app_include_js = "/assets/radicale_sync/js/radicale_sync.js"

# include js, css files in header of web template
# web_include_css = "/assets/radicale_sync/css/radicale_sync.css"
# web_include_js = "/assets/radicale_sync/js/radicale_sync.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "radicale_sync/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "radicale_sync/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "radicale_sync.utils.jinja_methods",
# 	"filters": "radicale_sync.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "radicale_sync.install.before_install"
# after_install = "radicale_sync.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "radicale_sync.uninstall.before_uninstall"
# after_uninstall = "radicale_sync.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "radicale_sync.utils.before_app_install"
# after_app_install = "radicale_sync.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "radicale_sync.utils.before_app_uninstall"
# after_app_uninstall = "radicale_sync.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "radicale_sync.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Contact": {
		"after_insert": "radicale_sync.radicale_sync.doctype.radicale_contacts.radicale_contacts.insert_contact_to_radicale",
		"on_update": "radicale_sync.radicale_sync.doctype.radicale_contacts.radicale_contacts.update_contact_in_radicale",
		"on_trash": "radicale_sync.radicale_sync.doctype.radicale_contacts.radicale_contacts.delete_contact_from_radicale",
	},
}

scheduler_events = {
	"cron": {
		"*/15 * * * *": [
			"radicale_sync.radicale_sync.doctype.radicale_contacts.radicale_contacts.sync_every_15_minutes",
		],
		"0 */4 * * *": [
			"radicale_sync.radicale_sync.doctype.radicale_contacts.radicale_contacts.sync_every_4_hours",
		],
	},
	"hourly": [
		"radicale_sync.radicale_sync.doctype.radicale_contacts.radicale_contacts.sync_hourly",
	],
	"daily": [
		"radicale_sync.radicale_sync.doctype.radicale_contacts.radicale_contacts.sync_daily",
	],
}


# Testing
# -------

# before_tests = "radicale_sync.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "radicale_sync.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "radicale_sync.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["radicale_sync.utils.before_request"]
# after_request = ["radicale_sync.utils.after_request"]

# Job Events
# ----------
# before_job = ["radicale_sync.utils.before_job"]
# after_job = ["radicale_sync.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"radicale_sync.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

