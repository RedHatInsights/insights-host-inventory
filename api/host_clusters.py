"""Fleet Profiles -- on-demand host clustering.

Groups an org's hosts into "profiles" (clusters) by the *set of installed package
names*, hard-partitioned by RHEL major version. Package versions and OS minor are
NOT clustering keys -- they are annotations used to score how uniformly patched a
cluster is. This mirrors the frontend's clusterModel.ts contract (HostClustersResponse).

Everything is computed on demand straight from the hosts tables: no new tables, no
materialized views, no migrations. That keeps the POC cheap to stand up; a production
version would precompute and cache.

Endpoints:
  GET /host-clusters                      -> {meta, clusters, outlier_host_ids}
  GET /host-clusters/{cluster_id}/hosts   -> {cluster_id, core_package_count, hosts}
  GET /host-clusters/outliers             -> {total, hosts}
"""

import hashlib
from collections import Counter
from collections import defaultdict
from datetime import UTC
from datetime import datetime

from sqlalchemy.orm import joinedload

from api import api_operation
from api import flask_json_response
from api import metrics
from app.auth import get_current_identity
from app.auth.rbac import KesselResourceTypes
from app.logging import get_logger
from app.models import Host
from app.models import db
from lib.middleware import access

logger = get_logger(__name__)

# Groups smaller than this don't earn the name "profile" -- their members become outliers.
MIN_CLUSTER_SIZE = 2
# How many host ids to surface inline on each cluster for quick preview.
SAMPLE_SIZE = 5
# Fuzzy clustering: a host joins a profile when its package-name set is at least this
# Jaccard-similar to the profile's seed set. 1.0 == the old exact-set behavior.
#
# Why 0.97 and not something lower: ~90 of every host's ~93 packages are the shared OS base
# (glibc, bash, systemd, ...), so even *different roles* start out ~0.94 similar to each other.
# That compresses all useful signal into the narrow 0.94-1.0 band. A loose bar like 0.90 then
# swallows whole roles (nginx + postgres + java merge into one blob); 0.97 keeps roles apart
# while still merging true within-role drift (e.g. 90 vs 91 shared packages == 0.989).
# A production version should weight packages by distinctiveness (down-weight ubiquitous base
# packages) so the threshold stops depending on base size -- tracked as a follow-up.
DEFAULT_THRESHOLD = 0.97
# A package is part of a profile's "core" (its expected manifest) when at least this
# fraction of members carry it. 0.5 == "half or more" (a majority), so a package held by
# 30 of 60 merged members becomes core -- and the other 30 see it as a "missing" to adopt.
DEFAULT_CONSENSUS = 0.5


def _jaccard(a, b):
    """Overlap of two sets: |a & b| / |a | b|. 1.0 == identical, 0.0 == disjoint."""
    union = len(a | b)
    return len(a & b) / union if union else 0.0


# --- NEVRA parsing -----------------------------------------------------------


def _parse_nevra(nevra):
    """``name-epoch:version-release.arch`` -> ``(name, version_release)``.

    Package names themselves contain hyphens (``postgresql-server``,
    ``java-17-openjdk``), so we anchor on the mandatory ``epoch:`` marker instead
    of naively splitting on ``-``.
    """
    try:
        left, right = nevra.split(":", 1)  # 'bash-0', '5.1.8-9.el8.x86_64'
        name = left.rsplit("-", 1)[0]  # 'bash'
        version_release = right.rsplit(".", 1)[0]  # drop arch -> '5.1.8-9.el8'
        return name, version_release
    except (ValueError, AttributeError):
        return nevra, ""


def _host_packages(host):
    """host -> {package_name: version_release} from the dynamic system profile."""
    dsp = host.dynamic_system_profile
    if not dsp or not dsp.installed_packages:
        return {}
    packages = {}
    for nevra in dsp.installed_packages:
        name, version_release = _parse_nevra(nevra)
        packages[name] = version_release
    return packages


def _host_os(host):
    """host -> (os_name, os_major, os_minor) from the static system profile."""
    ssp = host.static_system_profile
    operating_system = (ssp.operating_system if ssp else None) or {}
    return (
        operating_system.get("name"),
        operating_system.get("major"),
        operating_system.get("minor"),
    )


def _host_image(host):
    """host -> golden-image provenance from the static system profile.

    Returns (blueprint_id, blueprint_name, bootc_image). Any may be None. Image Profiles
    (api/image_profiles.py) use these to group hosts by the image/blueprint they were built
    from; the package clustering in this module ignores them.
    """
    ssp = host.static_system_profile
    image_builder = (ssp.image_builder if ssp else None) or {}
    bootc_status = (ssp.bootc_status if ssp else None) or {}
    booted = bootc_status.get("booted") or {}
    return (
        image_builder.get("blueprint_id"),
        image_builder.get("blueprint_name"),
        booted.get("image"),
    )


def _latest_minor(minors):
    """Highest numeric OS minor seen in a cluster (as a string), or None."""
    numeric = []
    for minor in minors:
        try:
            numeric.append(int(minor))
        except (ValueError, TypeError):
            continue
    return str(max(numeric)) if numeric else None


def _as_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return value


def _cluster_id(os_major, core_packages):
    """Deterministic id from (os_major, core package names).

    Must be stable across calls so the frontend can fetch /host-clusters and then
    /host-clusters/{id}/hosts and land on the same cluster.
    """
    digest = hashlib.md5(f"{os_major}|{','.join(core_packages)}".encode()).hexdigest()[:8]
    return f"cluster-rhel{os_major}-{digest}"


# --- Core computation --------------------------------------------------------


def _load_records(org_id):
    """One lightweight dict per host that has both package and OS data."""
    hosts = (
        db.session.query(Host)
        .filter(Host.org_id == org_id)
        .options(
            joinedload(Host.static_system_profile),
            joinedload(Host.dynamic_system_profile),
        )
        .all()
    )

    records = []
    for host in hosts:
        packages = _host_packages(host)
        os_name, os_major, os_minor = _host_os(host)
        if not packages or os_major is None:
            # No package set or no OS major -> nothing to cluster on.
            continue
        blueprint_id, blueprint_name, bootc_image = _host_image(host)
        records.append(
            {
                "id": str(host.id),
                "display_name": host.display_name,
                "os_name": os_name or "RHEL",
                "os_major": os_major,
                "os_minor": os_minor,
                "packages": packages,
                "names": frozenset(packages.keys()),
                "last_check_in": host.last_check_in,
                "groups": host.groups or [],
                "blueprint_id": blueprint_id,
                "blueprint_name": blueprint_name,
                "bootc_image": bootc_image,
            }
        )
    return records


def _is_current(record, baseline_versions, latest_minor):
    """True if the host is on the cluster baseline for every core package AND the
    latest OS minor seen in the cluster."""
    if latest_minor is not None and str(record["os_minor"]) != latest_minor:
        return False
    return all(record["packages"].get(name) == baseline for name, baseline in baseline_versions.items())


def _build_cluster(os_major, members, consensus=DEFAULT_CONSENSUS):
    """Assemble one cluster dict (minus label/percentage, filled in later).

    The core manifest = packages carried by at least `consensus` of members. With fuzzy
    grouping, members no longer share an identical name-set, so the core is a consensus
    rather than an exact intersection -- that's what makes "missing a core package" a real,
    actionable signal (adopt it) instead of always empty.
    """
    size = len(members)

    # How many members carry each package name? Core = those at/above the consensus bar.
    name_counts = Counter()
    for member in members:
        name_counts.update(member["names"])
    min_holders = consensus * size
    core_names = frozenset(name for name, count in name_counts.items() if count >= min_holders)
    core_packages = sorted(core_names)

    # Baseline = modal version-release among the members that actually HAVE each core
    # package. Laggards are the minority that trail it.
    baseline_versions = {}
    for name in core_packages:
        version_counts = Counter(member["packages"][name] for member in members if name in member["packages"])
        baseline_versions[name] = version_counts.most_common(1)[0][0]

    minor_distribution = Counter(str(member["os_minor"]) for member in members if member["os_minor"] is not None)
    latest_minor = _latest_minor(minor_distribution.keys())

    current = sum(1 for member in members if _is_current(member, baseline_versions, latest_minor))
    patch_currency = round(current / size, 2) if size else 0.0

    # Variability = how spread-out the group is, as a DISTANCE (0.0 = identical to core).
    # It is 1 - the mean Jaccard similarity of each member's name-set vs the consensus core.
    # The frontend renders (1 - variability) as "tightness".
    mean_similarity = sum(_jaccard(member["names"], core_names) for member in members) / size if size else 1.0
    variability = round(1 - mean_similarity, 2)

    return {
        "id": _cluster_id(os_major, core_packages),
        "label": "",  # assigned in _assign_labels once we know global distinctiveness
        "size": size,
        "percentage": 0.0,  # assigned once total clustered is known
        "core_packages": core_packages,
        "core_package_count": len(core_packages),
        "representative_host_id": members[0]["id"],
        "variability": variability,
        "sample_host_ids": [member["id"] for member in members[:SAMPLE_SIZE]],
        "os_name": members[0]["os_name"],
        "os_major": _as_int(os_major),
        "os_minor_distribution": dict(minor_distribution),
        "baseline_versions": baseline_versions,
        "patch_currency": patch_currency,
        "patch_laggards": size - current,
        "content_view": None,  # not derivable without Satellite facts in this POC
        "_members": members,
        "_core_names": core_names,
        "_latest_minor": latest_minor,
    }


def _assign_labels(clusters):
    """Give each cluster a human label built from its most *distinctive* core packages.

    A package shared by every cluster (glibc, bash, ...) says nothing; a package in
    only one cluster (nginx, redis, ...) names it. So rank each cluster's core by how
    few clusters contain it.
    """
    cluster_frequency = Counter()
    for cluster in clusters:
        for name in cluster["core_packages"]:
            cluster_frequency[name] += 1

    for cluster in clusters:
        distinctive = sorted(cluster["core_packages"], key=lambda name: (cluster_frequency[name], name))
        highlight = ", ".join(distinctive[:2]) if distinctive else "base packages"
        cluster["label"] = f"RHEL {cluster['os_major']} · {highlight}"


def _fuzzy_profiles(records, threshold):
    """Leader clustering within each OS major. Returns [(os_major, seed_names, members)].

    Identical name-sets are collapsed first (cheaper, and the biggest exact group is the
    most natural seed). Groups are then seeded largest-first; each remaining group joins
    the existing profile whose SEED name-set it is most similar to, if that similarity
    meets `threshold`. Judging membership against a stable seed (not transitively between
    members) is what stops a drift "chain" (90 -> 91 -> 92 pkgs) from snowballing every
    host into one blob.
    """
    exact = defaultdict(list)
    for record in records:
        exact[(str(record["os_major"]), record["names"])].append(record)

    # Largest exact group first; deterministic tie-break so ids are stable across requests.
    ordered = sorted(
        exact.items(),
        key=lambda item: (-len(item[1]), item[0][0], tuple(sorted(item[0][1]))),
    )

    profiles = []  # {"os_major": str, "seed": frozenset, "members": [record, ...]}
    for (os_major, names), members in ordered:
        best = None
        best_score = threshold  # must meet/beat threshold to join an existing profile
        for profile in profiles:
            if profile["os_major"] != os_major:
                continue
            score = _jaccard(names, profile["seed"])
            if score >= best_score:
                best_score = score
                best = profile
        if best is None:
            profiles.append({"os_major": os_major, "seed": names, "members": list(members)})
        else:
            best["members"].extend(members)

    return [(p["os_major"], p["seed"], p["members"]) for p in profiles]


def compute_fleet(org_id, threshold=DEFAULT_THRESHOLD, consensus=DEFAULT_CONSENSUS):
    """Cluster an org's hosts. Returns (clusters, outliers) of internal dicts.

    OS major is a hard partition wall; within it hosts group by package-name-set
    similarity at `threshold` (fuzzy). A profile's "core" manifest = packages held by at
    least `consensus` of its members.
    """
    records = _load_records(org_id)

    clusters = []
    outliers = []
    for os_major, _seed_names, members in _fuzzy_profiles(records, threshold):
        if len(members) < MIN_CLUSTER_SIZE:
            outliers.extend(members)
        else:
            clusters.append(_build_cluster(os_major, members, consensus))

    clusters.sort(key=lambda cluster: cluster["size"], reverse=True)
    _assign_labels(clusters)

    clustered_total = sum(cluster["size"] for cluster in clusters)
    for cluster in clusters:
        cluster["percentage"] = round(100 * cluster["size"] / clustered_total, 1) if clustered_total else 0.0

    return clusters, outliers


# --- Serialization -----------------------------------------------------------


def _public_cluster(cluster):
    """Strip the internal (underscore-prefixed) helper keys before returning."""
    return {key: value for key, value in cluster.items() if not key.startswith("_")}


def _nearest_cluster(record, clusters):
    """Best Jaccard match of a host's name-set against each cluster core, same OS major."""
    best = None
    best_score = 0.0
    for cluster in clusters:
        if str(cluster["os_major"]) != str(record["os_major"]):
            continue
        score = _jaccard(record["names"], cluster["_core_names"])
        if score > best_score:
            best_score = score
            best = cluster
    return best, round(best_score, 2)


def _patch_status(outdated_count, os_behind):
    """Map version/OS drift to the frontend's three-state PatchStatus."""
    if outdated_count == 0 and not os_behind:
        return "current"
    if outdated_count >= 2:
        return "behind"
    return "lagging"


def _host_delta(record, cluster):
    """One ClusterHostDelta: how a member host differs from its cluster baseline."""
    core = cluster["_core_names"]
    baseline_versions = cluster["baseline_versions"]
    latest_minor = cluster["_latest_minor"]

    extra_packages = sorted(record["names"] - core)
    missing_packages = sorted(core - record["names"])

    outdated_packages = []
    for name in sorted(core & record["names"]):
        installed = record["packages"].get(name)
        baseline = baseline_versions.get(name)
        if installed != baseline:
            outdated_packages.append({"name": name, "installed_version": installed, "baseline_version": baseline})

    os_behind = latest_minor is not None and str(record["os_minor"]) != latest_minor
    matched = len(record["names"] & core)
    union = len(record["names"] | core)

    return {
        "host_id": record["id"],
        "display_name": record["display_name"],
        "group_name": _group_name(record),
        "match_score": round(matched / union, 2) if union else 0.0,
        "extra_packages": extra_packages,
        "missing_packages": missing_packages,
        "extra_count": len(extra_packages),
        "missing_count": len(missing_packages),
        "outdated_packages": outdated_packages,
        "outdated_count": len(outdated_packages),
        "os_version": f"{record['os_major']}.{record['os_minor']}"
        if record["os_minor"] is not None
        else str(record["os_major"]),
        "os_behind": os_behind,
        "patch_status": _patch_status(len(outdated_packages), os_behind),
    }


def _group_name(record):
    """First workspace/group name on the host, for display. None if ungrouped-less."""
    for group in record["groups"]:
        if isinstance(group, dict) and group.get("name"):
            return group["name"]
    return None


# --- Handlers ----------------------------------------------------------------


@api_operation
@access(KesselResourceTypes.HOST.view)
@metrics.api_request_time.time()
def get_host_clusters(threshold=None, _min_cluster_size=None, _rbac_filter=None):
    org_id = get_current_identity().org_id
    effective_threshold = threshold if threshold is not None else DEFAULT_THRESHOLD
    clusters, outliers = compute_fleet(org_id, threshold=effective_threshold)

    clustered_hosts = sum(cluster["size"] for cluster in clusters)
    meta = {
        "total_hosts": clustered_hosts + len(outliers),
        "clustered_hosts": clustered_hosts,
        "outliers": len(outliers),
        "cluster_count": len(clusters),
        "axes": ["installed_packages"],
        "threshold": effective_threshold,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    response = {
        "meta": meta,
        "clusters": [_public_cluster(cluster) for cluster in clusters],
        "outlier_host_ids": [record["id"] for record in outliers],
    }
    logger.info("host-clusters computed for org %s: %s clusters, %s outliers", org_id, len(clusters), len(outliers))
    return flask_json_response(response)


@api_operation
@access(KesselResourceTypes.HOST.view)
@metrics.api_request_time.time()
def get_host_cluster_hosts(cluster_id, _rbac_filter=None):
    org_id = get_current_identity().org_id
    clusters, _ = compute_fleet(org_id)

    cluster = next((candidate for candidate in clusters if candidate["id"] == cluster_id), None)
    if cluster is None:
        return flask_json_response(
            {"detail": f"Cluster not found: {cluster_id}", "title": "Not Found", "status": 404}, status=404
        )

    response = {
        "cluster_id": cluster["id"],
        "core_package_count": cluster["core_package_count"],
        "hosts": [_host_delta(member, cluster) for member in cluster["_members"]],
    }
    return flask_json_response(response)


@api_operation
@access(KesselResourceTypes.HOST.view)
@metrics.api_request_time.time()
def get_host_cluster_outliers(_rbac_filter=None):
    org_id = get_current_identity().org_id
    clusters, outliers = compute_fleet(org_id)

    hosts = []
    for record in outliers:
        nearest, score = _nearest_cluster(record, clusters)
        core = nearest["_core_names"] if nearest else frozenset()
        hosts.append(
            {
                "host_id": record["id"],
                "display_name": record["display_name"],
                "nearest_cluster_id": nearest["id"] if nearest else None,
                "nearest_cluster_label": nearest["label"] if nearest else None,
                "nearest_match_score": score,
                "extra_packages": sorted(record["names"] - core),
                "missing_packages": sorted(core - record["names"]),
                "last_check_in": record["last_check_in"].isoformat() if record["last_check_in"] else None,
                "group_name": _group_name(record),
            }
        )

    return flask_json_response({"total": len(hosts), "hosts": hosts})
