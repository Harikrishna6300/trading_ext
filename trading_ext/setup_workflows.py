import frappe

ROLES = ["Trader", "Trade Manager", "Logistics User", "Finance Manager"]

CONTRACT_STATES = [
    # state, doc_status, role allowed to edit
    ("Draft", 0, "Trader"),
    ("Pending Approval", 0, "Trade Manager"),
    ("Approved", 1, "Trade Manager"),
    ("Rejected", 0, "Trader"),
    ("Cancelled", 2, "Trade Manager"),
]
CONTRACT_TRANSITIONS = [
    # from, action, to, role
    ("Draft", "Send for Approval", "Pending Approval", "Trader"),
    ("Pending Approval", "Approve", "Approved", "Trade Manager"),
    ("Pending Approval", "Reject", "Rejected", "Trade Manager"),
    ("Rejected", "Revise", "Draft", "Trader"),
    ("Approved", "Cancel", "Cancelled", "Trade Manager"),
]

SHIPMENT_STATES = [
    ("Draft", 0, "Logistics User"),
    ("Pending Finance Review", 0, "Finance Manager"),
    ("Approved", 1, "Logistics User"),
    ("Cancelled", 2, "Finance Manager"),
]
SHIPMENT_TRANSITIONS = [
    ("Draft", "Send for Review", "Pending Finance Review", "Logistics User"),
    ("Pending Finance Review", "Approve", "Approved", "Finance Manager"),
    ("Pending Finance Review", "Send Back", "Draft", "Finance Manager"),
    ("Approved", "Cancel", "Cancelled", "Finance Manager"),
]


def run():
    make_roles()
    make_workflow("Trade Contract Approval", "Trade Contract",
                  CONTRACT_STATES, CONTRACT_TRANSITIONS)
    make_workflow("Trade Shipment Approval", "Trade Shipment",
                  SHIPMENT_STATES, SHIPMENT_TRANSITIONS)
    frappe.db.commit()
    print("Workflows ready")


def make_roles():
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role,
                            "desk_access": 1}).insert(ignore_permissions=True)


def make_workflow(name, doctype, states, transitions):
    for state, _, _ in states:
        if not frappe.db.exists("Workflow State", state):
            frappe.get_doc({"doctype": "Workflow State",
                            "workflow_state_name": state}).insert(ignore_permissions=True)
    for _, action, _, _ in transitions:
        if not frappe.db.exists("Workflow Action Master", action):
            frappe.get_doc({"doctype": "Workflow Action Master",
                            "workflow_action_name": action}).insert(ignore_permissions=True)

    if frappe.db.exists("Workflow", name):
        frappe.delete_doc("Workflow", name, force=True)

    wf = frappe.new_doc("Workflow")
    wf.workflow_name = name
    wf.document_type = doctype
    wf.workflow_state_field = "workflow_state"
    wf.is_active = 1
    wf.send_email_alert = 0

    for state, doc_status, role in states:
        wf.append("states", {"state": state, "doc_status": str(doc_status),
                             "allow_edit": role})
    for src, action, dest, role in transitions:
        wf.append("transitions", {"state": src, "action": action,
                                  "next_state": dest, "allowed": role,
                                  "allow_self_approval": 1})
    wf.insert(ignore_permissions=True)