from app.auth import get_current_identity
from app.exceptions import InventoryException
from app.logging import get_logger
from app.models import AssignmentRule
from app.models import db
from lib.db import session_guard

logger = get_logger(__name__)


def add_assignment_rule(assign_rule_data, rbac_filter) -> AssignmentRule:
    logger.debug(f"Creating assignment rule: {assign_rule_data}")

    # Do not allow the user to create an assignment rule for a group they don't have access to
    if (
        rbac_filter is not None
        and "groups" in rbac_filter
        and len(rbac_groups := rbac_filter["groups"]) > 0
        and assign_rule_data.get("group_id") not in rbac_groups
    ):
        raise InventoryException(title="Forbidden", detail="User does not have permission for specified group.")

    org_id = get_current_identity().org_id
    account = get_current_identity().account_number
    assign_rule_name = assign_rule_data.get("name")
    filter = assign_rule_data.get("filter", {})
    enabled = assign_rule_data.get("enabled")
    group_id = assign_rule_data.get("group_id")
    description = assign_rule_data.get("description", None)

    with session_guard(db.session):
        new_assignment_rule = AssignmentRule(
            org_id=org_id, account=account, name=assign_rule_name, group_id=group_id, filter=filter, enabled=enabled
        )
        new_assignment_rule.description = description
        db.session.add(new_assignment_rule)
        db.session.flush()

    new_assignment_rule = AssignmentRule.query.filter(
        (AssignmentRule.name == assign_rule_name) & (AssignmentRule.org_id == org_id)
    ).one_or_none()
    return new_assignment_rule
