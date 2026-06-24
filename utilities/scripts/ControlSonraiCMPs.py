#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError

SONRAI_CMP_REGEX = re.compile(r"^SonraiCMP*")
SERVICE = "sso-admin"

# AWS Control Tower Landing Zone Permission Sets
LANDING_ZONE_PERMISSION_SETS = {
    "AWSServiceCatalogEndUserAccess",
    "AWSPowerUserAccess",
    "AWSAdministratorAccess",
    "AWSServiceCatalogAdminFullAccess",
    "AWSReadOnlyAccess",
    "AWSOrganizationsFullAccess",
}

# Cache file for Identity Center instance location
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".identity_center_cache.json")


def safe_call(fn, *args, **kwargs):
    """Call an AWS SDK function and return (result, error_str). Never raises."""
    try:
        return fn(*args, **kwargs), None
    except (ClientError, BotoCoreError, Exception) as e:
        return None, str(e)


def get_all_regions_for_sso() -> List[str]:
    session = boto3.session.Session()
    # Only regions that support sso-admin
    return session.get_available_regions(SERVICE)


def list_instances_in_region(region: str) -> List[Dict]:
    """Return list of {'InstanceArn':..., 'IdentityStoreId':...} in region."""
    client = boto3.client(SERVICE, region_name=region)
    paginator = client.get_paginator("list_instances")
    out = []
    try:
        for page in paginator.paginate():
            out.extend(page.get("Instances", []))
    except Exception as e:
        return
    return out


def list_permission_sets(client, instance_arn: str) -> List[str]:
    paginator = client.get_paginator("list_permission_sets")
    arns = []
    for page in paginator.paginate(InstanceArn=instance_arn):
        arns.extend(page.get("PermissionSets", []))
    return arns


def describe_permission_set(client, instance_arn: str, ps_arn: str) -> Dict:
    resp, err = safe_call(client.describe_permission_set, InstanceArn=instance_arn, PermissionSetArn=ps_arn)
    if err:
        raise RuntimeError(err)
    return resp.get("PermissionSet", {})


def list_cmp_refs(client, instance_arn: str, ps_arn: str) -> List[Dict]:
    paginator = client.get_paginator("list_customer_managed_policy_references_in_permission_set")
    refs = []
    for page in paginator.paginate(InstanceArn=instance_arn, PermissionSetArn=ps_arn):
        refs.extend(page.get("CustomerManagedPolicyReferences", []))
    return refs


def detach_cmp_ref(client, instance_arn: str, ps_arn: str, ref: Dict) -> Tuple[bool, str]:
    _, err = safe_call(
        client.detach_customer_managed_policy_reference_from_permission_set,
        InstanceArn=instance_arn,
        PermissionSetArn=ps_arn,
        CustomerManagedPolicyReference={"Name": ref["Name"], **({"Path": ref["Path"]} if "Path" in ref and ref["Path"] else {})},
    )
    return (err is None, err or "")


def attach_cmp_ref(client, instance_arn: str, ps_arn: str, ref: Dict) -> Tuple[bool, str]:
    _, err = safe_call(
        client.attach_customer_managed_policy_reference_to_permission_set,
        InstanceArn=instance_arn,
        PermissionSetArn=ps_arn,
        CustomerManagedPolicyReference={"Name": ref["Name"], **({"Path": ref["Path"]} if "Path" in ref and ref["Path"] else {})},
    )
    return (err is None, err or "")


def provision_permission_set(client, instance_arn: str, ps_arn: str) -> Tuple[bool, str]:
    """
    Provision the permission set to all accounts where it's currently assigned.
    Returns (success, error_message).
    """
    _, err = safe_call(
        client.provision_permission_set,
        InstanceArn=instance_arn,
        PermissionSetArn=ps_arn,
        TargetType="ALL_PROVISIONED_ACCOUNTS",
    )
    return (err is None, err or "")


def get_local_sonrai_cmps() -> List[Dict]:
    """
    Discover local (account) IAM customer-managed policies that match SonraiCMPs.
    Returns list of dicts with keys Name and Path.
    """
    iam = boto3.client("iam")
    paginator = iam.get_paginator("list_policies")
    found = []
    for page in paginator.paginate(Scope="Local"):  # only customer-managed
        for pol in page.get("Policies", []):
            name = pol.get("PolicyName", "")
            path = pol.get("Path", "/")
            if SONRAI_CMP_REGEX.match(name):
                found.append({"Name": name, "Path": path or "/"})
    return found


def read_cache() -> Optional[Dict]:
    """Read the cached Identity Center instance location."""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


def write_cache(region: str, instance_arn: str, identity_store_id: str) -> None:
    """Write the Identity Center instance location to cache."""
    try:
        cache_data = {
            "region": region,
            "instance_arn": instance_arn,
            "identity_store_id": identity_store_id,
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to write cache file: {e}")


def find_identity_center_instance() -> Optional[Tuple[str, Dict]]:
    """
    Find the Identity Center instance, using cache if available.
    Returns (region, instance_dict) or None if not found.
    """
    # Try cache first
    cache = read_cache()
    if cache:
        region = cache.get("region")
        instance_arn = cache.get("instance_arn")
        identity_store_id = cache.get("identity_store_id")
        if region and instance_arn and identity_store_id:
            # Verify cache is still valid
            try:
                client = boto3.client(SERVICE, region_name=region)
                client.describe_instance(InstanceArn=instance_arn)
                print(f"Using cached Identity Center instance in {region}")
                return region, {"InstanceArn": instance_arn, "IdentityStoreId": identity_store_id}
            except Exception:
                print("Cached instance is no longer valid, searching all regions...")

    # Cache miss or invalid - search all regions
    print("Searching all regions for an Identity Center instance...")
    regions = get_all_regions_for_sso()
    for region in regions:
        instances = list_instances_in_region(region)
        if instances:
            # Found an instance - cache it and return
            inst = instances[0]  # Use first instance found
            write_cache(region, inst["InstanceArn"], inst["IdentityStoreId"])
            print(f"Found Identity Center instance in {region} (cached for future runs)")
            return region, inst

    return None


def detach_mode(dry_run: bool = False):
    mode_str = "Mode: DETACH SonraiCMPs from Landing Zone permission sets"
    if dry_run:
        mode_str += " (DRY RUN)"
    print(mode_str)

    total_actions = 0
    total_errors = 0
    impacted_permission_sets = []  # Track (client, region, instance_arn, ps_arn, ps_name) for provisioning

    # Find Identity Center instance (using cache if available)
    result = find_identity_center_instance()
    if not result:
        print("No Identity Center instance found in any region.")
        return

    region, inst = result
    inst_arn = inst["InstanceArn"]
    client = boto3.client(SERVICE, region_name=region)

    print(f"\n[{region}] Instance: {inst_arn}")
    try:
        ps_arns = list_permission_sets(client, inst_arn)
    except Exception as e:
        print(f"[{region}] Error listing permission sets: {e}")
        return

    for ps_arn in ps_arns:
        try:
            ps = describe_permission_set(client, inst_arn, ps_arn)
            name = ps.get("Name", "")
        except Exception as e:
            print(f"[{region}] Describe failed for {ps_arn}: {e}")
            total_errors += 1
            continue

        # Filter for Landing Zone permission sets only
        if name not in LANDING_ZONE_PERMISSION_SETS:
            continue

        try:
            refs = list_cmp_refs(client, inst_arn, ps_arn)
        except Exception as e:
            print(f"[{region}] List CMP refs failed for {name}: {e}")
            total_errors += 1
            continue

        targets = [r for r in refs if SONRAI_CMP_REGEX.match(r.get("Name", ""))]
        if not targets:
            continue

        ps_modified = False
        for ref in targets:
            if dry_run:
                print(f"[{region}] [DRY RUN] Would detach {ref['Name']} (path {ref.get('Path','/')}) from permission set {name}")
                total_actions += 1
                ps_modified = True
            else:
                ok, err = detach_cmp_ref(client, inst_arn, ps_arn, ref)
                if ok:
                    print(f"[{region}] Detached {ref['Name']} (path {ref.get('Path','/')}) from permission set {name}")
                    total_actions += 1
                    ps_modified = True
                else:
                    print(f"[{region}] Failed to detach {ref.get('Name','?')} from {name}: {err}")
                    total_errors += 1

        if ps_modified and not dry_run:
            impacted_permission_sets.append((client, region, inst_arn, ps_arn, name))

    # Provision impacted permission sets
    if impacted_permission_sets and not dry_run:
        print("\nProvisioning impacted permission sets...")
        for client, region, inst_arn, ps_arn, name in impacted_permission_sets:
            ok, err = provision_permission_set(client, inst_arn, ps_arn)
            if ok:
                print(f"[{region}] Provisioned permission set {name}")
            else:
                print(f"[{region}] Failed to provision {name}: {err}")
                total_errors += 1

    print("\nSummary:")
    print(f"Actions performed: {total_actions}")
    print(f"Errors encountered: {total_errors}")
    if total_errors > 0:
        sys.exit(2)


def attach_mode(dry_run: bool = False):
    mode_str = "Mode: ATTACH SonraiCMPs back to Landing Zone permission sets where missing"
    if dry_run:
        mode_str += " (DRY RUN)"
    print(mode_str)

    local_cmps = get_local_sonrai_cmps()
    if not local_cmps:
        print("No local IAM customer-managed policies that start with SonraiCMP. Nothing to attach.")
        return

    print("Local policies discovered:")
    for ref in local_cmps:
        print(f"  {ref['Name']} (path {ref['Path']})")

    total_actions = 0
    total_errors = 0
    impacted_permission_sets = []  # Track (client, region, instance_arn, ps_arn, ps_name) for provisioning

    # Find Identity Center instance (using cache if available)
    result = find_identity_center_instance()
    if not result:
        print("No Identity Center instance found in any region.")
        return

    region, inst = result
    inst_arn = inst["InstanceArn"]
    client = boto3.client(SERVICE, region_name=region)

    print(f"\n[{region}] Instance: {inst_arn}")
    try:
        ps_arns = list_permission_sets(client, inst_arn)
    except Exception as e:
        print(f"[{region}] Error listing permission sets: {e}")
        return

    for ps_arn in ps_arns:
        try:
            ps = describe_permission_set(client, inst_arn, ps_arn)
            name = ps.get("Name", "")
        except Exception as e:
            print(f"[{region}] Describe failed for {ps_arn}: {e}")
            total_errors += 1
            continue

        # Filter for Landing Zone permission sets only
        if name not in LANDING_ZONE_PERMISSION_SETS:
            continue

        try:
            existing_refs = list_cmp_refs(client, inst_arn, ps_arn)
        except Exception as e:
            print(f"[{region}] List CMP refs failed for {name}: {e}")
            total_errors += 1
            continue

        existing_set = {(r.get("Name", ""), r.get("Path", "/") or "/") for r in existing_refs}
        ps_modified = False
        for ref in local_cmps:
            key = (ref["Name"], ref.get("Path", "/") or "/")
            if key in existing_set:
                continue
            if dry_run:
                print(f"[{region}] [DRY RUN] Would attach {ref['Name']} (path {ref['Path']}) to permission set {name}")
                total_actions += 1
                ps_modified = True
            else:
                ok, err = attach_cmp_ref(client, inst_arn, ps_arn, ref)
                if ok:
                    print(f"[{region}] Attached {ref['Name']} (path {ref['Path']}) to permission set {name}")
                    total_actions += 1
                    ps_modified = True
                else:
                    print(f"[{region}] Failed to attach {ref['Name']} to {name}: {err}")
                    total_errors += 1

        if ps_modified and not dry_run:
            impacted_permission_sets.append((client, region, inst_arn, ps_arn, name))

    # Provision impacted permission sets
    if impacted_permission_sets and not dry_run:
        print("\nProvisioning impacted permission sets...")
        for client, region, inst_arn, ps_arn, name in impacted_permission_sets:
            ok, err = provision_permission_set(client, inst_arn, ps_arn)
            if ok:
                print(f"[{region}] Provisioned permission set {name}")
            else:
                print(f"[{region}] Failed to provision {name}: {err}")
                total_errors += 1

    print("\nSummary:")
    print(f"Actions performed: {total_actions}")
    print(f"Errors encountered: {total_errors}")
    if total_errors > 0:
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser(
        description="Detach or attach Sonrai customer-managed policies on Landing Zone permission sets across all Identity Center instances/regions."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--detach", action="store_true", help="Detach SonraiCMPs from Landing Zone permission sets")
    group.add_argument("--attach", action="store_true", help="Re-attach SonraiCMPs to Landing Zone permission sets (undo)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")

    args = parser.parse_args()

    if not args.detach and not args.attach:
        parser.print_help(sys.stderr)
        sys.exit(1)

    if args.detach:
        detach_mode(dry_run=args.dry_run)
    elif args.attach:
        attach_mode(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

