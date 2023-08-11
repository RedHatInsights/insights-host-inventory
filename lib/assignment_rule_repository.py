from app.auth import get_current_identity
from app.logging import get_logger
from app.models import AssignmentRule
from app.models import db
from lib.db import session_guard


logger = get_logger(__name__)


def add_assignment_rule(assign_rule_data) -> AssignmentRule:
    logger.debug(f"Creating assignment rule: {assign_rule_data}")
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
