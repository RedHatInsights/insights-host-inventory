import pytest

from iqe_host_inventory.utils.tag_utils import convert_tag_to_string

pytestmark = [pytest.mark.backend]


@pytest.mark.ephemeral
def test_cert_auth_tags(
    hbi_setup_tagged_hosts_for_identity_cert_auth,
    host_inventory_system_correct,
):
    """
    Test that I can only get tags of the hosts with the same owner ID as my host has when using
    cert auth.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-12040

    metadata:
        requirements: inv-api-cert-auth, inv-tags-get-list
        assignee: fstavela
        importance: high
        title: Inventory: get tags using cert auth
    """
    correct_owner_id_tag = hbi_setup_tagged_hosts_for_identity_cert_auth["correct_owner_id_tag"]
    correct_owner_id_tag_str = convert_tag_to_string(correct_owner_id_tag)
    without_owner_id_tag_str = convert_tag_to_string(
        hbi_setup_tagged_hosts_for_identity_cert_auth["without_owner_id_tag"]
    )
    wrong_owner_id_tag_str = convert_tag_to_string(
        hbi_setup_tagged_hosts_for_identity_cert_auth["wrong_owner_id_tag"]
    )

    # Using host with the same owner ID
    response = host_inventory_system_correct.apis.tags.get_tags_response(
        tags=[correct_owner_id_tag_str]
    )
    assert response.count == 1
    assert response.results[0].tag.to_dict() == correct_owner_id_tag

    # Using host without owner ID
    response = host_inventory_system_correct.apis.tags.get_tags_response(
        tags=[without_owner_id_tag_str]
    )
    assert response.count == 0

    # Using host with different owner ID
    response = host_inventory_system_correct.apis.tags.get_tags_response(
        tags=[wrong_owner_id_tag_str]
    )
    assert response.count == 0


@pytest.mark.ephemeral
def test_cert_auth_tags_search(
    hbi_setup_tagged_hosts_for_identity_cert_auth,
    host_inventory_system_correct,
):
    """
    Test that I can only search for tags of the hosts with the same owner ID as my host has when
    using cert auth.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-12040

    metadata:
        requirements: inv-api-cert-auth, inv-tags-get-list
        assignee: fstavela
        importance: high
        title: Inventory: search for tags using cert auth
    """
    correct_owner_id_tag = hbi_setup_tagged_hosts_for_identity_cert_auth["correct_owner_id_tag"]
    correct_owner_id_tag_str = convert_tag_to_string(correct_owner_id_tag)
    without_owner_id_tag_str = convert_tag_to_string(
        hbi_setup_tagged_hosts_for_identity_cert_auth["without_owner_id_tag"]
    )
    wrong_owner_id_tag_str = convert_tag_to_string(
        hbi_setup_tagged_hosts_for_identity_cert_auth["wrong_owner_id_tag"]
    )

    # Using host with the same owner ID
    response = host_inventory_system_correct.apis.tags.get_tags_response(
        search=correct_owner_id_tag_str
    )
    assert response.count == 1
    assert response.results[0].tag.to_dict() == correct_owner_id_tag

    # Using host without owner ID
    response = host_inventory_system_correct.apis.tags.get_tags_response(
        search=without_owner_id_tag_str
    )
    assert response.count == 0

    # Using host with different owner ID
    response = host_inventory_system_correct.apis.tags.get_tags_response(
        search=wrong_owner_id_tag_str
    )
    assert response.count == 0
