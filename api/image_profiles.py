"""Image Profiles -- on-demand grouping of hosts by the golden image / blueprint they
were built from, with drift and consolidation guidance.

This is the provenance-first companion to Fleet Profiles (api/host_clusters.py). Where that
module discovers profiles bottom-up from installed-package similarity, this one groups hosts
top-down by an explicit image identity carried on the host:

  * Image Builder blueprint  -> system_profile.image_builder.blueprint_id
  * bootc / immutable image  -> system_profile.bootc_status.booted.image

For every image profile we surface two actionable groups:

  * "Built from this image"  -- hosts that carry the provenance, and how each has DRIFTED
                                from the image's expected manifest (extra / missing / outdated
                                packages, OS-minor lag). Answers "are my golden-image hosts
                                still in spec?"
  * "Best-fit candidates"    -- hosts WITHOUT this provenance whose package set is already
                                >= threshold similar to the image manifest. Answers "which
                                ad-hoc hosts could I rebuild from this image to standardize?"

A single host can legitimately appear as built-from one image AND a candidate for another, so
these profiles are intentionally a separate view from the single-assignment Fleet Profiles.

Everything is computed on demand from the hosts tables -- no new tables, same POC posture as
host_clusters. The image manifest is derived as the consensus core of the built-from hosts
(a production version would use the blueprint's declared package list instead).

Endpoints:
  GET /image-profiles                      -> {meta, image_profiles}
  GET /image-profiles/{image_id}/hosts     -> {image_id, built_from, candidates}
"""

import hashlib
from collections import Counter
from collections import defaultdict
from datetime import UTC
from datetime import datetime

from api import api_operation
from api import flask_json_response
from api import metrics
from api.host_clusters import DEFAULT_CONSENSUS
from api.host_clusters import DEFAULT_THRESHOLD
from api.host_clusters import SAMPLE_SIZE
from api.host_clusters import _host_delta
from api.host_clusters import _is_current
from api.host_clusters import _jaccard
from api.host_clusters import _latest_minor
from api.host_clusters import _load_records
from app.auth import get_current_identity
from app.auth.rbac import KesselResourceTypes
from app.logging import get_logger
from lib.middleware import access

logger = get_logger(__name__)

# Need at least this many built-from hosts before an image is worth profiling; otherwise its
# hosts fall back into the candidate pool for the other images.
MIN_IMAGE_HOSTS = 2
# Cap the candidate list we materialize per image (the count is still reported in full).
MAX_CANDIDATES = 50


def _image_identity(record, ambient_bootc):
    """record -> (kind, key, name) of its curated image, or None.

    A blueprint id always wins. A bootc image counts only when it is NOT the fleet's ambient
    image: nearly every host boots the same base bootc image (the fixture/default), which is
    noise, not a curated golden image -- treating it as a profile would lump the whole fleet
    into one meaningless bucket.
    """
    blueprint_id = record.get("blueprint_id")
    if blueprint_id:
        name = record.get("blueprint_name") or f"Blueprint {str(blueprint_id)[:8]}"
        return "blueprint", str(blueprint_id), name
    bootc_image = record.get("bootc_image")
    if bootc_image and bootc_image != ambient_bootc:
        return "bootc", bootc_image, bootc_image
    return None


def _image_id(kind, key):
    """Stable, URL-safe id for an image profile (key may be a UUID or an image ref)."""
    digest = hashlib.md5(f"{kind}|{key}".encode()).hexdigest()[:8]
    return f"image-{kind}-{digest}"


def _build_manifest(members, consensus):
    """The image's expected manifest, derived from its built-from hosts.

    Returns (core_names, baseline_versions, minor_distribution, latest_minor). Core = package
    names held by at least `consensus` of members; baseline = modal version among members that
    carry each core package. This mirrors host_clusters._build_cluster so drift math lines up.
    """
    size = len(members)
    name_counts = Counter()
    for member in members:
        name_counts.update(member["names"])
    min_holders = consensus * size
    core_names = frozenset(name for name, count in name_counts.items() if count >= min_holders)

    baseline_versions = {}
    for name in sorted(core_names):
        version_counts = Counter(member["packages"][name] for member in members if name in member["packages"])
        baseline_versions[name] = version_counts.most_common(1)[0][0]

    minor_distribution = Counter(str(member["os_minor"]) for member in members if member["os_minor"] is not None)
    latest_minor = _latest_minor(minor_distribution.keys())
    return core_names, baseline_versions, minor_distribution, latest_minor


def compute_image_profiles(org_id, threshold=DEFAULT_THRESHOLD, consensus=DEFAULT_CONSENSUS):
    """Group an org's hosts by curated image provenance. Returns (profiles, ambient_bootc).

    Each profile dict carries the internal keys `_members`, `_candidates`, `_core_names`,
    `baseline_versions`, `_latest_minor` so _host_delta() can be reused verbatim for both the
    built-from and candidate host lists.
    """
    records = _load_records(org_id)

    bootc_counts = Counter(record["bootc_image"] for record in records if record["bootc_image"])
    ambient_bootc = bootc_counts.most_common(1)[0][0] if bootc_counts else None

    built = defaultdict(list)
    meta_by_key = {}
    pool = []  # hosts with no curated image -> candidate pool for every profile
    for record in records:
        identity = _image_identity(record, ambient_bootc)
        if identity is None:
            pool.append(record)
            continue
        kind, key, name = identity
        built[key].append(record)
        meta_by_key[key] = (kind, name)

    profiles = []
    for key, members in built.items():
        if len(members) < MIN_IMAGE_HOSTS:
            pool.extend(members)  # too small to profile; still usable as candidates elsewhere
            continue
        kind, name = meta_by_key[key]
        core_names, baseline_versions, minor_distribution, latest_minor = _build_manifest(members, consensus)
        os_major = Counter(str(member["os_major"]) for member in members).most_common(1)[0][0]
        current = sum(1 for member in members if _is_current(member, baseline_versions, latest_minor))
        size = len(members)
        profiles.append(
            {
                "id": _image_id(kind, key),
                "kind": kind,  # 'blueprint' | 'bootc'
                "name": name,
                "image_ref": key,
                "os_name": members[0]["os_name"],
                "os_major": os_major,
                "os_minor_distribution": dict(minor_distribution),
                "built_from_count": size,
                "core_package_count": len(core_names),
                "core_packages": sorted(core_names),
                "baseline_versions": baseline_versions,
                "patch_currency": round(current / size, 2) if size else 0.0,
                "drifted_count": size - current,
                "sample_host_ids": [member["id"] for member in members[:SAMPLE_SIZE]],
                "_members": members,
                "_core_names": core_names,
                "_latest_minor": latest_minor,
            }
        )

    # Best-fit candidates: pooled hosts (no curated image) that already resemble the manifest.
    for profile in profiles:
        scored = []
        for record in pool:
            if str(record["os_major"]) != str(profile["os_major"]):
                continue
            score = _jaccard(record["names"], profile["_core_names"])
            if score >= threshold:
                scored.append((score, record))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        profile["candidate_count"] = len(scored)
        profile["_candidates"] = [record for _score, record in scored[:MAX_CANDIDATES]]

    _label_profiles(profiles)
    profiles.sort(key=lambda profile: profile["built_from_count"], reverse=True)
    return profiles, ambient_bootc


def _label_profiles(profiles):
    """Give blueprint profiles a human label from their most *distinctive* core packages.

    Image Builder's blueprint_id is an opaque UUID and the system-profile schema has no field
    for a blueprint name, so a bare id tells a user nothing. We borrow host_clusters' approach:
    rank each profile's core by how few OTHER profiles share each package, and headline the
    rarest. bootc profiles already carry a meaningful image ref, so they keep their name.
    """
    profile_frequency = Counter()
    for profile in profiles:
        for name in profile["core_packages"]:
            profile_frequency[name] += 1

    for profile in profiles:
        if profile["kind"] != "blueprint":
            continue
        distinctive = sorted(profile["core_packages"], key=lambda name: (profile_frequency[name], name))
        highlight = ", ".join(distinctive[:2]) if distinctive else "base packages"
        profile["name"] = f"Blueprint · RHEL {profile['os_major']} · {highlight}"


def _public_image_profile(profile):
    """Strip internal (underscore-prefixed) keys before returning to the client."""
    return {key: value for key, value in profile.items() if not key.startswith("_")}


# --- Handlers ----------------------------------------------------------------


@api_operation
@access(KesselResourceTypes.HOST.view)
@metrics.api_request_time.time()
def get_image_profiles(threshold=None, _rbac_filter=None):
    org_id = get_current_identity().org_id
    effective_threshold = threshold if threshold is not None else DEFAULT_THRESHOLD
    profiles, ambient_bootc = compute_image_profiles(org_id, threshold=effective_threshold)

    meta = {
        "image_profile_count": len(profiles),
        "built_from_total": sum(profile["built_from_count"] for profile in profiles),
        "candidate_total": sum(profile["candidate_count"] for profile in profiles),
        "ambient_bootc_image": ambient_bootc,
        "threshold": effective_threshold,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    response = {
        "meta": meta,
        "image_profiles": [_public_image_profile(profile) for profile in profiles],
    }
    logger.info("image-profiles computed for org %s: %s profiles", org_id, len(profiles))
    return flask_json_response(response)


@api_operation
@access(KesselResourceTypes.HOST.view)
@metrics.api_request_time.time()
def get_image_profile_hosts(image_id, _rbac_filter=None):
    org_id = get_current_identity().org_id
    profiles, _ = compute_image_profiles(org_id)

    profile = next((candidate for candidate in profiles if candidate["id"] == image_id), None)
    if profile is None:
        return flask_json_response(
            {"detail": f"Image profile not found: {image_id}", "title": "Not Found", "status": 404},
            status=404,
        )

    response = {
        "image_id": profile["id"],
        "name": profile["name"],
        "kind": profile["kind"],
        "core_package_count": profile["core_package_count"],
        "built_from": [_host_delta(member, profile) for member in profile["_members"]],
        "candidates": [_host_delta(record, profile) for record in profile["_candidates"]],
    }
    return flask_json_response(response)
