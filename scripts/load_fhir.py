#!/usr/bin/env python3
"""Load Synthea FHIR transaction bundles into a FHIR server.

Usage:
    python scripts/load_fhir.py --bundles dataset/synthea \
        --base-url https://hapi.fhir.org/baseR4

Posts hospital/practitioner bundles first, then each patient bundle as a
transaction. If the transaction POST fails (e.g. nginx 413 on bundles that
exceed the server's body limit, or HAPI rejecting inline match URLs), falls
back to posting entries one resource at a time, rewriting urn:uuid references
to server-assigned ids and resolving conditional `Type?param=value`
references via search.

Writes dataset/patient_ids.json mapping server-assigned patient ids to names
and birth dates.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = REPO_ROOT / "dataset" / "patient_ids.json"

MAX_RETRIES = 3
FHIR_JSON = {"Content-Type": "application/fhir+json"}
UUID_PREFIX = "urn:uuid:"
COND_REF = re.compile(r"^([A-Z][A-Za-z]+)\?(.+)$")


def post_bundle(client: httpx.Client, base_url: str, bundle: dict) -> dict | None:
    url = base_url.rstrip("/") + "/"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.post(url, json=bundle, headers=FHIR_JSON)
        except httpx.TransportError as exc:
            print(f"    transport error (attempt {attempt}/{MAX_RETRIES}): {exc}")
            if attempt == MAX_RETRIES:
                return None
            time.sleep(2 ** attempt)
            continue
        if resp.status_code < 400:
            return resp.json()
        print(f"    HTTP {resp.status_code} (attempt {attempt}/{MAX_RETRIES})")
        try:
            print(f"    {json.dumps(resp.json(), indent=2)[:2000]}")
        except ValueError:
            print(f"    {resp.text[:2000]}")
        if 400 <= resp.status_code < 500:
            return None  # 4xx: don't retry, report and continue
        if attempt == MAX_RETRIES:
            return None
        time.sleep(2 ** attempt)
    return None


def iter_references(node):
    """Yield (dict, key, value) for every {"reference": str} in a resource."""
    if isinstance(node, dict):
        ref = node.get("reference")
        if isinstance(ref, str):
            yield ref
        for value in node.values():
            yield from iter_references(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_references(item)


def rewrite_references(node, id_map: dict, resolve_conditional) -> None:
    """Rewrite urn:uuid and conditional references in place."""
    if isinstance(node, dict):
        ref = node.get("reference")
        if isinstance(ref, str):
            if ref in id_map:
                node["reference"] = id_map[ref]
            elif COND_REF.match(ref):
                resolved = resolve_conditional(ref)
                if resolved:
                    node["reference"] = resolved
        for value in node.values():
            rewrite_references(value, id_map, resolve_conditional)
    elif isinstance(node, list):
        for item in node:
            rewrite_references(item, id_map, resolve_conditional)


def unresolved_uuids(node, id_map: dict, bundle_uuids: set[str]) -> bool:
    """True if node references a uuid that is another bundle entry not yet created."""
    return any(
        ref.startswith(UUID_PREFIX) and ref in bundle_uuids and ref not in id_map
        for ref in iter_references(node)
    )


def post_entries_individually(client: httpx.Client, base_url: str,
                              bundle: dict) -> dict[str, str]:
    """Fallback loader: create each entry with individual POSTs.

    Returns a map of bundle fullUrl -> server-assigned 'Type/id'.
    """
    base = base_url.rstrip("/")
    entries = [e for e in bundle.get("entry", []) if e.get("resource")]
    bundle_uuids = {e.get("fullUrl") for e in entries}
    id_map: dict[str, str] = {}
    cond_cache: dict[str, str | None] = {}

    def resolve_conditional(ref: str) -> str | None:
        if ref in cond_cache:
            return cond_cache[ref]
        rtype, query = ref.split("?", 1)
        resolved = None
        try:
            resp = client.get(f"{base}/{rtype}?{query}", headers={"Accept": "application/fhir+json"})
            if resp.status_code < 400:
                for entry in resp.json().get("entry", []):
                    res = entry.get("resource", {})
                    if res.get("id"):
                        resolved = f"{rtype}/{res['id']}"
                        break
        except (httpx.TransportError, ValueError):
            pass
        if not resolved:
            print(f"    could not resolve conditional ref {ref}")
        cond_cache[ref] = resolved
        return resolved

    failed = 0
    pending = entries
    while pending:
        still_pending = []
        progressed = False
        for entry in pending:
            res = entry["resource"]
            if unresolved_uuids(res, id_map, bundle_uuids):
                still_pending.append(entry)
                continue
            rewrite_references(res, id_map, resolve_conditional)
            rtype = res["resourceType"]
            ok = False
            for attempt in range(1, 3):
                try:
                    resp = client.post(f"{base}/{rtype}", json=res, headers=FHIR_JSON)
                except httpx.TransportError as exc:
                    print(f"    {rtype}: transport error: {exc}")
                    continue
                if resp.status_code < 400:
                    created = resp.json()
                    if entry.get("fullUrl"):
                        id_map[entry["fullUrl"]] = f"{rtype}/{created['id']}"
                    ok = True
                    break
                if resp.status_code == 412:
                    # server rejected a duplicate; reuse the existing resource id
                    match = re.search(rf"{rtype}/\d+", resp.text)
                    if match and entry.get("fullUrl"):
                        id_map[entry["fullUrl"]] = match.group(0)
                        ok = True
                        break
                if attempt == 2:
                    try:
                        diag = resp.json()["issue"][0].get("diagnostics", "")
                    except (ValueError, KeyError, IndexError):
                        diag = resp.text[:300]
                    print(f"    {rtype}: HTTP {resp.status_code}: {diag[:300]}")
            if ok:
                progressed = True
                created_so_far = len(id_map)
                if created_so_far % 100 == 0:
                    print(f"    ... {created_so_far}/{len(entries)} created")
            else:
                failed += 1
                if entry.get("fullUrl"):
                    # mark so dependents don't wait forever on this uuid
                    bundle_uuids.discard(entry["fullUrl"])
        if len(id_map) % 100:
            print(f"    ... {len(id_map)}/{len(entries)} created, {len(still_pending)} deferred")
        if not progressed and still_pending:
            print(f"    {len(still_pending)} entries skipped: unresolvable references")
            failed += len(still_pending)
            break
        pending = still_pending

    if failed:
        print(f"    {failed} entries failed")
    return id_map


def patient_identity(bundle: dict) -> tuple[str | None, str | None]:
    """Pull name and birthDate out of the Patient resource in the request bundle."""
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") != "Patient":
            continue
        name_parts = []
        for name in res.get("name", []):
            given = " ".join(name.get("given", []))
            family = name.get("family", "")
            full = f"{given} {family}".strip()
            if full:
                name_parts.append(full)
        return (name_parts[0] if name_parts else None), res.get("birthDate")
    return None, None


def patient_server_id(result: dict, bundle: dict) -> str | None:
    """Server Patient id from a transaction response bundle."""
    for entry in result.get("entry", []):
        location = (entry.get("response") or {}).get("location", "")
        if location.startswith("Patient/"):
            # location may be "Patient/123/_history/1"
            return "/".join(location.split("/")[:2])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles", default="dataset/synthea",
                        help="Directory containing Synthea FHIR bundle JSON files")
    parser.add_argument("--base-url",
                        default=os.environ.get("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4"),
                        help="FHIR server base URL (env FHIR_BASE_URL)")
    args = parser.parse_args()

    bundles_dir = Path(args.bundles)
    if not bundles_dir.is_absolute():
        bundles_dir = REPO_ROOT / bundles_dir
    files = sorted(bundles_dir.glob("*.json"))
    if not files:
        print(f"No bundle files found in {bundles_dir}", file=sys.stderr)
        return 1

    hospitals = [f for f in files if f.name.startswith("hospitalInformation")]
    practitioners = [f for f in files if f.name.startswith("practitionerInformation")]
    patients = [f for f in files
                if not f.name.startswith("hospitalInformation")
                and not f.name.startswith("practitionerInformation")]
    print(f"Found {len(hospitals)} hospital, {len(practitioners)} practitioner, "
          f"{len(patients)} patient bundles in {bundles_dir}")
    print(f"Posting to {args.base_url}")

    patient_ids: list[dict] = []
    with httpx.Client(timeout=120) as client:
        for path in hospitals + practitioners:
            print(f"POST {path.name} ...")
            result = post_bundle(client, args.base_url, json.loads(path.read_text()))
            print(f"  -> {'ok' if result else 'FAILED'}")

        for i, path in enumerate(patients, 1):
            bundle = json.loads(path.read_text())
            name, birth_date = patient_identity(bundle)
            print(f"[{i}/{len(patients)}] POST {path.name} ({name or 'unknown'}) ...")
            result = post_bundle(client, args.base_url, bundle)
            if result:
                server_id = patient_server_id(result, bundle)
                if not server_id:
                    print("  -> no Patient location in response, skipping")
                    continue
            else:
                print("  -> transaction failed, posting entries individually")
                id_map = post_entries_individually(client, args.base_url, bundle)
                server_id = None
                for entry in bundle.get("entry", []):
                    if entry.get("resource", {}).get("resourceType") == "Patient":
                        server_id = id_map.get(entry.get("fullUrl"))
                        break
                if not server_id:
                    print("  -> FAILED (no Patient created), skipping")
                    continue
            print(f"  -> {server_id}")
            patient_ids.append({
                "fhirPatientId": server_id,
                "name": name,
                "birthDate": birth_date,
                "base_url": args.base_url,
            })

    OUT_FILE.write_text(json.dumps(patient_ids, indent=2))
    print(f"Wrote {len(patient_ids)} patient ids to {OUT_FILE}")
    return 0 if patient_ids else 1


if __name__ == "__main__":
    sys.exit(main())
