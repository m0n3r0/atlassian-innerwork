import json
from pathlib import Path

_ALLOWED_PLATFORM_DEPENDENCIES = {
    "identity",
    "teams",
    "goals",
    "search",
    "chat",
    "studio",
    "analytics",
    "admin",
    "audit",
    "billing",
    "rovo",
}


def _catalog() -> dict:
    return json.loads(Path("data/product_catalog.json").read_text())


def test_product_catalog_has_required_shape():
    catalog = _catalog()

    assert catalog["source"] == "https://www.atlassian.com/software"
    assert catalog["source_reviewed_at"]
    assert catalog["products"]
    assert catalog["families"]
    assert catalog["collections"]
    assert catalog["platform_capabilities"]
    assert set(catalog["edge_profiles"])


def test_every_product_has_family_profile_source_and_positioning():
    catalog = _catalog()
    families = {family["id"] for family in catalog["families"]}
    profiles = set(catalog["edge_profiles"])
    object_types = {"product", "homepage_capability", "ecosystem_resource"}

    for product in catalog["products"]:
        assert product["id"]
        assert product["name"]
        assert product["object_type"] in object_types
        assert product["family"] in families
        assert product["homepage_positioning"]
        assert product["system_role"]
        assert product["edge_profile"] in profiles
        assert product["platform_dependencies"]
        assert product["source_url"] == catalog["source"]


def test_product_ids_are_unique_and_family_membership_is_consistent():
    catalog = _catalog()
    product_ids = [product["id"] for product in catalog["products"]]
    assert len(product_ids) == len(set(product_ids))

    by_id = {product["id"]: product for product in catalog["products"]}
    family_members = set()
    for family in catalog["families"]:
        assert family["products"]
        for product_id in family["products"]:
            assert product_id in by_id
            assert by_id[product_id]["family"] == family["id"]
            family_members.add(product_id)

    assert family_members == set(product_ids)


def test_collections_reference_catalog_products():
    catalog = _catalog()
    product_ids = {product["id"] for product in catalog["products"]}

    for collection in catalog["collections"]:
        assert collection["id"]
        assert collection["items"]
        assert collection["homepage_positioning"]
        for item in collection["items"]:
            assert item in product_ids


def test_platform_dependencies_resolve():
    catalog = _catalog()
    product_ids = {product["id"] for product in catalog["products"]}
    platform_ids = {capability["id"] for capability in catalog["platform_capabilities"]}
    allowed = product_ids | platform_ids | _ALLOWED_PLATFORM_DEPENDENCIES

    for product in catalog["products"]:
        unresolved = set(product["platform_dependencies"]) - allowed
        assert not unresolved, f"{product['id']} has unresolved dependencies: {sorted(unresolved)}"


def test_every_edge_profile_is_defined_and_used():
    catalog = _catalog()
    defined_profiles = set(catalog["edge_profiles"])
    used_profiles = {product["edge_profile"] for product in catalog["products"]}

    assert used_profiles <= defined_profiles
    assert defined_profiles == used_profiles


def test_catalog_contains_all_homepage_products_and_resource_surfaces_modeled_in_docs():
    product_ids = {product["id"] for product in _catalog()["products"]}

    expected = {
        "jira",
        "confluence",
        "loom",
        "trello",
        "rovo",
        "jira_service_management",
        "customer_service_management",
        "assets",
        "statuspage",
        "guard",
        "bitbucket",
        "pipelines",
        "rovo_dev",
        "dx",
        "jira_product_discovery",
        "feedback",
        "focus",
        "talent",
        "jira_align",
        "bamboo",
        "sourcetree",
        "marketplace",
        "community",
        "partners",
        "developer_resources",
    }

    assert expected.issubset(product_ids)


def test_expected_public_collections_are_locked():
    catalog = _catalog()
    collections = {collection["id"]: collection["items"] for collection in catalog["collections"]}

    assert collections == {
        "teamwork_collection": ["jira", "confluence", "loom"],
        "strategy_collection": ["focus", "talent", "jira_align"],
        "service_collection": ["jira_service_management", "customer_service_management", "assets"],
        "software_collection": ["rovo_dev", "dx", "pipelines", "bitbucket"],
        "product_collection": ["jira_product_discovery", "feedback", "rovo"],
    }


def test_expected_cloud_platform_capabilities_are_locked():
    catalog = _catalog()
    platform_ids = {capability["id"] for capability in catalog["platform_capabilities"]}

    assert platform_ids == {
        "home",
        "goals",
        "teams",
        "studio",
        "search",
        "chat",
        "analytics",
        "admin",
    }


def test_allowed_shared_dependencies_are_documented():
    assert _ALLOWED_PLATFORM_DEPENDENCIES == {
        "identity",
        "teams",
        "goals",
        "search",
        "chat",
        "studio",
        "analytics",
        "admin",
        "audit",
        "billing",
        "rovo",
    }
