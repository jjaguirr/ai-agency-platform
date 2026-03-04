"""Validate workflow template structure and content."""
from typing import Dict, List, Tuple


REQUIRED_FIELDS = {"name", "description", "category", "triggers", "actions"}
VALID_TRIGGER_TYPES = {"schedule", "event", "webhook", "message"}
VALID_ACTION_TYPES = {
    "generate_content", "schedule_post", "notify_customer",
    "send_email", "log_crm", "generate_invoice", "log_accounting",
    "classify_lead", "enrich_data", "route_lead", "notify_sales",
    "check_availability", "propose_times", "confirm_booking",
    "send_reminder", "aggregate_metrics", "generate_report",
    "store_report", "send_welcome", "schedule_discovery_call",
    "conduct_business_discovery", "create_first_automation",
    "wait",
}


def validate_template(template: Dict) -> Tuple[bool, List[str]]:
    """Validate a workflow template. Returns (is_valid, errors)."""
    errors = []

    missing = REQUIRED_FIELDS - set(template.keys())
    if missing:
        errors.append(f"Missing required fields: {missing}")

    for trigger in template.get("triggers", []):
        if trigger.get("type") not in VALID_TRIGGER_TYPES:
            errors.append(f"Invalid trigger type: {trigger.get('type')}")

    for action in template.get("actions", []):
        if action.get("type") not in VALID_ACTION_TYPES:
            errors.append(f"Unknown action type: {action.get('type')}")

    return len(errors) == 0, errors
