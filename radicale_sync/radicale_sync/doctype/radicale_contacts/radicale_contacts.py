# Copyright (c) 2026, Frappe Community and contributors
# License: MIT. See LICENSE
"""
CardDAV contact synchronisation between a Radicale (or any CardDAV) server
and ERPNext Contacts.

Each Radicale Contacts record carries its own connection credentials:
host, port, SSL, path, username, password.

Pull: Reads vCards from the server and creates/updates ERPNext Contact records.
Push: Writes ERPNext Contact records back to the server as vCards.
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import requests

import frappe
from frappe import _
from frappe.model.document import Document


class RadicaleContacts(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        account_name: DF.Data
        carddav_path: DF.Data | None
        delete_on_remove: DF.Check
        enable: DF.Check
        last_sync_on: DF.Datetime | None
        on_remote_conflict: DF.Literal["Overwrite Remote", "Skip"]
        on_remote_delete: DF.Literal["Recreate on Server", "Delete Locally", "Ignore"]
        password: DF.Password
        port: DF.Int
        pull_from_radicale: DF.Check
        push_to_radicale: DF.Check
        server_host: DF.Data
        sync_interval: DF.Literal["Every 15 Minutes", "Hourly", "Every 4 Hours", "Daily"]
        sync_token: DF.SmallText | None
        use_ssl: DF.Check
        username: DF.Data
        verify_ssl: DF.Check

    # end: auto-generated types

    def on_update(self):
        """Delete pulled contacts when the account is disabled or pull is turned off."""
        was_enabled = bool(self.get_doc_before_save() and self.get_doc_before_save().enable)
        was_pulling = bool(self.get_doc_before_save() and self.get_doc_before_save().pull_from_radicale)

        disabled = was_enabled and not self.enable
        pull_turned_off = was_pulling and not self.pull_from_radicale

        if disabled or pull_turned_off:
            _delete_pulled_contacts(self.name)

    def get_base_url(self) -> str:
        scheme = "https" if self.use_ssl else "http"
        host = (self.server_host or "").rstrip("/")
        port = self.port or 5232
        return f"{scheme}://{host}:{port}"

    def get_session(self) -> requests.Session:
        session = requests.Session()
        session.auth = (
            self.username or "",
            self.get_password(fieldname="password", raise_exception=False) or "",
        )
        session.verify = bool(self.verify_ssl) if self.use_ssl else False
        session.headers.update({"Content-Type": "application/xml; charset=utf-8"})
        return session

    def get_address_book_url(self) -> str:
        base = self.get_base_url()
        if self.carddav_path:
            path = self.carddav_path.strip("/")
            return f"{base}/{path}/"
        url = _discover_addressbook_url(self.get_session(), base)
        if url:
            self.db_set("carddav_path", url.replace(base, "").strip("/"))
            return url.rstrip("/") + "/"
        frappe.throw(_("Could not discover CardDAV address book URL. Please set the path manually."))


def _delete_pulled_contacts(account_name: str):
    """Delete all contacts that were pulled from the given Radicale Contacts account."""
    contacts = frappe.get_list(
        "Contact",
        filters={"radicale_contacts": account_name, "pulled_from_radicale": 1},
        pluck="name",
    )
    for name in contacts:
        frappe.delete_doc("Contact", name, ignore_permissions=True, force=True)
    if contacts:
        frappe.msgprint(
            _("{0} contact(s) removed because sync was disabled for this account.").format(
                len(contacts)
            ),
            alert=True,
        )


# ── Scheduler dispatchers (one per supported interval) ────────────────────────


def _sync_by_interval(interval: str):
    """Run sync for all enabled accounts configured for *interval*."""
    for name in frappe.get_list(
        "Radicale Contacts",
        filters={"enable": 1, "sync_interval": interval},
        pluck="name",
    ):
        try:
            sync_contacts(name)
        except Exception as exc:
            frappe.log_error(str(exc), f"Radicale Scheduled Sync {name}")


def sync_every_15_minutes():
    _sync_by_interval("Every 15 Minutes")


def sync_every_4_hours():
    _sync_by_interval("Every 4 Hours")


def sync_daily():
    _sync_by_interval("Daily")


def sync_hourly():
    _sync_by_interval("Hourly")


# ── Whitelist APIs ─────────────────────────────────────────────────────────────


@frappe.whitelist()
def sync(radicale_contact: str | None = None):
    """Sync all enabled (or a specific) Radicale Contacts account."""
    filters = {"enable": 1}
    if radicale_contact:
        filters["name"] = radicale_contact

    messages = []
    for name in frappe.get_list("Radicale Contacts", filters=filters, pluck="name"):
        messages.append(sync_contacts(name))
    return messages


@frappe.whitelist()
def test_connection(radicale_contact: str) -> dict:
    """Test server connectivity for a Radicale Contacts account."""
    account: RadicaleContacts = frappe.get_doc("Radicale Contacts", radicale_contact)
    account.check_permission("read")
    base = account.get_base_url()
    session = account.get_session()
    body = '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'
    try:
        resp = session.request(
            "PROPFIND", base + "/",
            data=body.encode(),
            headers={"Depth": "0"},
            timeout=10,
        )
        if resp.status_code in (200, 207):
            return {"success": True, "message": _("Connected to {0}").format(base)}
        return {"success": False, "message": _("Server returned HTTP {0}").format(resp.status_code)}
    except requests.exceptions.SSLError as exc:
        return {"success": False, "message": _("SSL error: {0}").format(str(exc))}
    except requests.exceptions.ConnectionError as exc:
        return {"success": False, "message": _("Connection error: {0}").format(str(exc))}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


# ── Core sync ──────────────────────────────────────────────────────────────────


def sync_contacts(account_name: str) -> str:
    """Bidirectional sync for one Radicale Contacts account."""
    account: RadicaleContacts = frappe.get_doc("Radicale Contacts", account_name)
    session = account.get_session()
    ab_url = account.get_address_book_url()

    pulled = pushed = 0

    if account.pull_from_radicale:
        pulled = _pull_contacts(session, account, ab_url)

    if account.push_to_radicale:
        pushed = _push_contacts(session, account, ab_url)

    account.db_set("last_sync_on", frappe.utils.now_datetime())

    parts = []
    if pulled:
        parts.append(_("{0} contact(s) pulled").format(pulled))
    if pushed:
        parts.append(_("{0} contact(s) pushed").format(pushed))
    return ", ".join(parts) if parts else _("No contacts changed.")


# ── Pull (CardDAV → ERPNext) ───────────────────────────────────────────────────


def _pull_contacts(session, account: "RadicaleContacts", ab_url: str) -> int:
    """Fetch vCards from the server and upsert ERPNext Contacts."""
    try:
        import vobject
    except ImportError:
        frappe.throw(
            _("The 'vobject' Python library is required. Install it with: pip install vobject")
        )

    # REPORT addressbook-query to fetch all vcards
    report_body = (
        '<card:addressbook-query xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
        "<d:prop>"
        "<d:getetag/>"
        "<card:address-data/>"
        "</d:prop>"
        "</card:addressbook-query>"
    )
    try:
        root = _report(session, ab_url, report_body)
    except Exception as exc:
        frappe.log_error(str(exc), "Radicale Contacts Pull Error")
        return 0

    count = 0
    for response_el in root.findall("{DAV:}response"):
        href_el = response_el.find("{DAV:}href")
        vcard_el = response_el.find(
            ".//{urn:ietf:params:xml:ns:carddav}address-data"
        )
        if vcard_el is None or not vcard_el.text:
            continue

        vcard_text = vcard_el.text.strip()
        href = href_el.text.strip() if href_el is not None else ""
        # Normalise href to a bare filename stem (matches _propfind_etags key format)
        href_stem = href.rsplit("/", 1)[-1]
        if href_stem.lower().endswith(".vcf"):
            href_stem = href_stem[:-4]

        try:
            vcard = list(vobject.readComponents(vcard_text))[0]
            _upsert_contact_from_vcard(vcard, account, href_stem)
            count += 1
        except Exception as exc:
            frappe.log_error(
                f"href={href}\n{vcard_text}\n\n{exc}", "Radicale Contacts vCard Parse Error"
            )

    return count


def _upsert_contact_from_vcard(vcard, account: "RadicaleContacts", href: str):
    """Create or update a Frappe Contact from a parsed vCard."""
    uid = _vcard_uid(vcard) or href

    # Determine name components
    first_name = last_name = middle_name = salutation = ""
    if hasattr(vcard, "n"):
        n = vcard.n.value
        first_name = (n.given or "").strip()
        last_name = (n.family or "").strip()
        additional = (n.additional or "").strip()
        middle_name = additional
        salutation = (n.prefix or "").strip()
    elif hasattr(vcard, "fn"):
        parts = (vcard.fn.value or "").split(" ", 2)
        first_name = parts[0] if parts else ""
        last_name = parts[-1] if len(parts) > 1 else ""

    designation = ""
    if hasattr(vcard, "title"):
        designation = (vcard.title.value or "").strip()

    # Existing contact?
    existing_name = frappe.db.get_value(
        "Contact", {"radicale_uid": uid, "radicale_contacts": account.name}, "name"
    )

    if existing_name:
        contact = frappe.get_doc("Contact", existing_name)
        contact.first_name = first_name or contact.first_name
        contact.last_name = last_name
        contact.middle_name = middle_name
        if salutation:
            contact.salutation = salutation
        if designation:
            contact.designation = designation
        _sync_vcard_emails(contact, vcard)
        _sync_vcard_phones(contact, vcard)
        # Suppress push-back hook so saving during pull doesn't re-push to server
        contact.flags.skip_radicale_push = True
        contact.save(ignore_permissions=True)
    else:
        contact = frappe.get_doc(
            {
                "doctype": "Contact",
                "first_name": first_name or "Unknown",
                "last_name": last_name,
                "middle_name": middle_name,
                "salutation": salutation or None,
                "designation": designation or None,
                "radicale_uid": uid,
                "radicale_contacts": account.name,
                "pulled_from_radicale": 1,
            }
        )
        _sync_vcard_emails(contact, vcard)
        _sync_vcard_phones(contact, vcard)
        # Suppress push-back hook; pulled_from_radicale=1 already guards after_insert,
        # but set the flag explicitly for safety.
        contact.flags.skip_radicale_push = True
        contact.insert(ignore_permissions=True)


def _vcard_uid(vcard) -> str | None:
    if hasattr(vcard, "uid"):
        return (vcard.uid.value or "").strip() or None
    return None


def _sync_vcard_emails(contact, vcard):
    contact.email_ids = []
    if hasattr(vcard, "email_list"):
        for i, email_prop in enumerate(vcard.email_list):
            email_val = (email_prop.value or "").strip()
            if email_val:
                contact.add_email(email_id=email_val, is_primary=1 if i == 0 else 0)


def _sync_vcard_phones(contact, vcard):
    contact.phone_nos = []
    if hasattr(vcard, "tel_list"):
        for i, tel_prop in enumerate(vcard.tel_list):
            tel_val = (tel_prop.value or "").strip()
            if tel_val:
                contact.add_phone(phone=tel_val, is_primary_phone=1 if i == 0 else 0)


# ── Push (ERPNext → CardDAV) ───────────────────────────────────────────────────


def _push_contacts(session, account: "RadicaleContacts", ab_url: str) -> int:
    """Push ERPNext Contacts to the server, respecting remote-delete and conflict settings."""
    try:
        import vobject  # noqa: F401
    except ImportError:
        frappe.throw(
            _("The 'vobject' Python library is required. Install it with: pip install vobject")
        )

    on_remote_delete = account.on_remote_delete or "Recreate on Server"
    on_remote_conflict = account.on_remote_conflict or "Overwrite Remote"

    # Fetch current server state: {uid: etag}
    server_cards = _propfind_etags(session, ab_url)

    contacts = frappe.get_list(
        "Contact",
        filters={"radicale_contacts": account.name, "sync_with_radicale": 1},
        pluck="name",
    )

    pushed = 0
    for contact_name in contacts:
        contact = frappe.get_doc("Contact", contact_name)
        try:
            uid = contact.get("radicale_uid") or str(uuid.uuid4())
            if not contact.get("radicale_uid"):
                frappe.db.set_value("Contact", contact.name, "radicale_uid", uid)

            card_url = urljoin(ab_url, f"{uid}.vcf")
            server_etag = server_cards.get(uid)
            stored_etag = contact.get("radicale_etag") or None

            if server_etag is None:
                # Contact does not exist on the server
                if on_remote_delete == "Delete Locally":
                    frappe.delete_doc("Contact", contact.name, ignore_permissions=True, force=True)
                    continue
                elif on_remote_delete == "Ignore":
                    continue
                # else: "Recreate on Server" — fall through to PUT
            else:
                # Contact exists on server — check for remote changes via ETag
                if stored_etag and server_etag != stored_etag:
                    # Remote was changed since we last pushed
                    if on_remote_conflict == "Skip":
                        continue
                    # else: "Overwrite Remote" — fall through to PUT

            vcard_str = _contact_to_vcard(contact, uid)
            resp = _put(session, card_url, vcard_str, "text/vcard; charset=utf-8")
            # Store the ETag returned by the server so we can detect future remote changes
            new_etag = resp.headers.get("ETag") or resp.headers.get("etag")
            if new_etag:
                frappe.db.set_value("Contact", contact.name, "radicale_etag", new_etag.strip('"'))
            pushed += 1
        except Exception as exc:
            frappe.log_error(str(exc), f"Radicale Push Contact {contact.name}")

    return pushed


def _propfind_etags(session: "requests.Session", ab_url: str) -> dict:
    """Return {uid: etag} for all cards currently on the server."""
    body = '<d:propfind xmlns:d="DAV:"><d:prop><d:getetag/></d:prop></d:propfind>'
    try:
        resp = session.request(
            "PROPFIND", ab_url, data=body.encode(),
            headers={"Depth": "1"}, timeout=30,
        )
        resp.raise_for_status()
        import xml.etree.ElementTree as _ET
        root = _ET.fromstring(resp.content)
    except Exception as exc:
        frappe.log_error(str(exc), "Radicale PROPFIND ETags Error")
        return {}

    result = {}
    for resp_el in root.findall("{DAV:}response"):
        href_el = resp_el.find("{DAV:}href")
        etag_el = resp_el.find(".//{DAV:}getetag")
        if href_el is None or etag_el is None:
            continue
        href = href_el.text.strip()
        if not href.endswith(".vcf"):
            continue
        uid = href.rsplit("/", 1)[-1][:-4]  # strip path and .vcf
        result[uid] = (etag_el.text or "").strip().strip('"')
    return result


def _get_contact_address(contact) -> dict | None:
    """Return an Address dict for the contact, falling back to linked Customer/Supplier/Company."""
    address_fields = ["address_line1", "address_line2", "city", "state", "pincode", "country"]

    def _addr_by_link(link_doctype: str, link_name: str, primary_only: bool = False) -> str | None:
        filters = [
            ["Dynamic Link", "link_doctype", "=", link_doctype],
            ["Dynamic Link", "link_name", "=", link_name],
        ]
        if primary_only:
            filters.append(["is_primary_address", "=", 1])
        results = frappe.get_list("Address", filters=filters, pluck="name", limit=1)
        return results[0] if results else None

    def _first_addr(link_doctype: str, link_name: str) -> str | None:
        return _addr_by_link(link_doctype, link_name, primary_only=True) or \
               _addr_by_link(link_doctype, link_name)

    # 1. Direct address link on the Contact record
    addr_name = contact.get("address")

    # 2. Dynamic-link address for this Contact
    if not addr_name:
        addr_name = _first_addr("Contact", contact.name)

    # 3. Fall back to each linked Customer / Supplier / Company in the contact's links table
    if not addr_name:
        for link_row in contact.get("links") or []:
            link_doctype = link_row.get("link_doctype")
            link_name = link_row.get("link_name")
            if not (link_doctype and link_name):
                continue
            addr_name = _first_addr(link_doctype, link_name)
            if addr_name:
                break

    # 4. Last resort: match by company_name text against Company documents
    if not addr_name:
        company_name = contact.get("company_name")
        if company_name:
            # Try exact Company document match
            addr_name = _first_addr("Company", company_name)
            # Try Customer with that name
            if not addr_name:
                addr_name = _first_addr("Customer", company_name)

    if not addr_name:
        return None

    return frappe.db.get_value("Address", addr_name, address_fields, as_dict=True)


def _get_company_from_links(contact) -> str | None:
    """Return the company name from the contact's linked documents.

    Checks each row in the contact's links table in order:
    - Customer  → customer_name field
    - Supplier  → supplier_name field
    - Company   → name (the Company name is the document name)
    Returns the first non-empty value found.
    """
    for link_row in contact.get("links") or []:
        link_doctype = link_row.get("link_doctype")
        link_name = link_row.get("link_name")
        if not (link_doctype and link_name):
            continue
        if link_doctype == "Customer":
            val = frappe.db.get_value("Customer", link_name, "customer_name")
        elif link_doctype == "Supplier":
            val = frappe.db.get_value("Supplier", link_name, "supplier_name")
        elif link_doctype == "Company":
            val = link_name
        else:
            continue
        if val:
            return str(val)
    return None


def _contact_to_vcard(contact, uid: str) -> str:
    """Render an ERPNext Contact as a vCard 3.0 string."""
    import vobject

    vcard = vobject.vCard()
    vcard.add("uid").value = uid
    vcard.add("fn").value = (
        " ".join(
            filter(
                None,
                [contact.salutation, contact.first_name, contact.middle_name, contact.last_name],
            )
        )
        or contact.name
    )
    n = vobject.vcard.Name(
        family=contact.last_name or "",
        given=contact.first_name or "",
        additional=contact.middle_name or "",
        prefix=contact.salutation or "",
    )
    vcard.add("n").value = n

    if contact.get("designation"):
        vcard.add("title").value = contact.designation

    for email_row in contact.get("email_ids") or []:
        email_val = email_row.get("email_id") or ""
        if email_val:
            vcard.add("email").value = email_val

    for phone_row in contact.get("phone_nos") or []:
        phone_val = phone_row.get("phone") or ""
        if phone_val:
            vcard.add("tel").value = phone_val

    addr = _get_contact_address(contact)
    if addr:
        vcard.add("adr").value = vobject.vcard.Address(
            street=addr.get("address_line1") or "",
            extended=addr.get("address_line2") or "",
            city=addr.get("city") or "",
            region=addr.get("state") or "",
            code=addr.get("pincode") or "",
            country=addr.get("country") or "",
        )

    org = contact.get("company_name") or _get_company_from_links(contact)
    if org:
        vcard.add("org").value = [org]

    return vcard.serialize()


# ── Document events (push on save/delete) ─────────────────────────────────────


def insert_contact_to_radicale(doc, method=None):
    """Hook: after_insert on Contact."""
    if doc.flags.get("skip_radicale_push"):
        return
    _push_contact_event(doc)


def update_contact_in_radicale(doc, method=None):
    """Hook: on_update on Contact."""
    if doc.flags.get("skip_radicale_push"):
        return
    before = doc.get_doc_before_save()
    # If push was just disabled, delete from server
    if before and before.get("sync_with_radicale") and not doc.get("sync_with_radicale"):
        _delete_contact_from_server(doc)
        return
    _push_contact_event(doc)


def delete_contact_from_radicale(doc, method=None):
    """Hook: on_trash on Contact."""
    _delete_contact_from_server(doc)


def _delete_contact_from_server(doc):
    """Delete contact from Radicale server if the account is configured to do so."""
    radicale_contacts = doc.get("radicale_contacts")
    uid = doc.get("radicale_uid")
    if not (radicale_contacts and uid):
        return
    try:
        account: RadicaleContacts = frappe.get_doc("Radicale Contacts", radicale_contacts)
        if not account.enable or not account.push_to_radicale:
            return
        if not account.delete_on_remove:
            return
        session = account.get_session()
        ab_url = account.get_address_book_url()
        _delete(session, urljoin(ab_url, f"{uid}.vcf"))
        # Clear UID/ETag so a future re-enable starts fresh
        frappe.db.set_value("Contact", doc.name, {"radicale_uid": None, "radicale_etag": None})
    except Exception as exc:
        frappe.log_error(str(exc), f"Radicale Delete Contact {doc.name}")


def _push_contact_event(doc):
    """Push a single contact to Radicale on save."""
    try:
        import vobject  # noqa: F401
    except ImportError:
        return

    radicale_contacts = doc.get("radicale_contacts")
    if not radicale_contacts or doc.get("pulled_from_radicale") or not doc.get("sync_with_radicale"):
        return

    try:
        account: RadicaleContacts = frappe.get_doc("Radicale Contacts", radicale_contacts)
        if not account.enable or not account.push_to_radicale:
            return
        session = account.get_session()
        ab_url = account.get_address_book_url()
        uid = doc.get("radicale_uid") or str(uuid.uuid4())
        if not doc.get("radicale_uid"):
            frappe.db.set_value("Contact", doc.name, "radicale_uid", uid)
            doc.radicale_uid = uid  # keep in-memory doc in sync so on_update reuses the same UID
        vcard_str = _contact_to_vcard(doc, uid)
        resp = _put(session, urljoin(ab_url, f"{uid}.vcf"), vcard_str, "text/vcard; charset=utf-8")
        new_etag = resp.headers.get("ETag") or resp.headers.get("etag")
        if new_etag:
            frappe.db.set_value("Contact", doc.name, "radicale_etag", new_etag.strip('"'))
    except Exception as exc:
        frappe.log_error(str(exc), f"Radicale Push Contact {doc.name}")


# ── Low-level HTTP helpers ─────────────────────────────────────────────────────


def _report(session: requests.Session, url: str, body: str) -> ET.Element:
    resp = session.request(
        "REPORT", url, data=body.encode("utf-8"), headers={"Depth": "1"}, timeout=60
    )
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def _put(session: requests.Session, url: str, data: str, content_type: str):
    resp = session.put(
        url, data=data.encode("utf-8"), headers={"Content-Type": content_type}, timeout=30
    )
    resp.raise_for_status()
    return resp


def _delete(session: requests.Session, url: str):
    resp = session.delete(url, timeout=30)
    resp.raise_for_status()
    return resp


def _discover_addressbook_url(session: requests.Session, base_url: str) -> str | None:
    """Best-effort CardDAV address book discovery via PROPFIND."""
    propfind_body = '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'

    def propfind(url: str, depth: str = "0", body: str = propfind_body) -> ET.Element | None:
        try:
            r = session.request(
                "PROPFIND", url, data=body.encode(),
                headers={"Depth": depth}, timeout=15,
            )
            r.raise_for_status()
            return ET.fromstring(r.content)
        except Exception:
            return None

    root = propfind(base_url.rstrip("/") + "/")
    if root is None:
        return None

    principal_el = root.find(".//{DAV:}current-user-principal/{DAV:}href")
    if principal_el is None or not principal_el.text:
        return None
    principal_url = urljoin(base_url, principal_el.text.strip())

    ab_body = (
        '<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
        "<d:prop><card:addressbook-home-set/></d:prop></d:propfind>"
    )
    root2 = propfind(principal_url, body=ab_body)
    if root2 is None:
        return None

    home_el = root2.find(".//{urn:ietf:params:xml:ns:carddav}addressbook-home-set/{DAV:}href")
    if home_el is None or not home_el.text:
        return None
    home_url = urljoin(base_url, home_el.text.strip())

    root3 = propfind(home_url, depth="1")
    if root3 is not None:
        for resp_el in root3.findall("{DAV:}response"):
            href_el = resp_el.find("{DAV:}href")
            ab_el = resp_el.find(".//{DAV:}resourcetype/{urn:ietf:params:xml:ns:carddav}addressbook")
            if href_el is not None and ab_el is not None:
                candidate = urljoin(base_url, href_el.text.strip())
                if candidate.rstrip("/") != home_url.rstrip("/"):
                    return candidate.rstrip("/") + "/"

    return home_url.rstrip("/") + "/"
