#!/usr/bin/env python3
"""Approve (or revoke) a doctor account — the documented local verification mechanism.

WHAT THIS IS
    The prototype stands in for a real credential check: someone with access to the
    deployment verifies the doctor's medical registration number out of band, then marks
    the account verified. This script is that "someone", for local development.

WHY IT IS NOT A BACKDOOR
    Running it requires write access to the server's account store — i.e. you are
    already the operator of the deployment. It exposes no network surface, accepts no
    token, and cannot be triggered by a signup, a request body, or any API call. A person
    creating a doctor account through the UI cannot reach it.

    There is no universal OTP, no "dev doctor" mobile number, and no flag anywhere that
    grants doctor privileges without a deliberate approval recorded here or through
    POST /v1/auth/admin/doctors/{id}/verify.

USAGE
    .venv/bin/python scripts/approve_doctor.py --list
    .venv/bin/python scripts/approve_doctor.py --mobile +919876543210
    .venv/bin/python scripts/approve_doctor.py --account-id acc_... --revoke

FOR PRODUCTION
    Replace this with a real verification workflow: a reviewer UI backed by
    POST /v1/auth/admin/doctors/{id}/verify, an NMC registry lookup, and an audit record
    of who approved whom. `service.approve_doctor()` is the single function every route
    goes through, so that swap touches one layer.
"""
from __future__ import annotations

# Run directly from a clone without installing the package: the repo root has to be on
# sys.path for `import src.*`. `make setup` also writes a .pth, but this script must work
# for someone who just cloned and ran it.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import sys

from src.auth import service
from src.auth.models import Role, mask_mobile
from src.auth.storage import get_auth_store


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mobile", help="mobile number of the doctor account")
    ap.add_argument("--account-id", help="account id of the doctor account")
    ap.add_argument("--revoke", action="store_true",
                    help="remove verification instead of granting it")
    ap.add_argument("--reason", default=None, help="reason, recorded when revoking")
    ap.add_argument("--list", action="store_true",
                    help="list doctor accounts and their verification state")
    args = ap.parse_args()

    store = get_auth_store()

    if args.list or not (args.mobile or args.account_id):
        doctors = store.list_accounts(Role.DOCTOR.value)
        if not doctors:
            print("No doctor accounts yet.")
            print(f"(account store: {store.dir})")
            return 0
        print(f"{'ACCOUNT ID':<24} {'MOBILE':<20} {'VERIFIED':<9} REGISTRATION")
        for a in doctors:
            prof = a.doctor_profile or {}
            print(f"{a.account_id:<24} {mask_mobile(a.mobile):<20} "
                  f"{str(a.doctor_verified):<9} "
                  f"{prof.get('registration_number','—')} · {prof.get('doctor_name','—')}")
        if not args.list:
            print("\nPass --mobile or --account-id to approve one.")
        return 0

    acc = (store.get(args.account_id) if args.account_id
           else store.get_by_mobile(args.mobile))
    if acc is None:
        print(f"No account found for {args.account_id or args.mobile}", file=sys.stderr)
        return 1
    if acc.role != Role.DOCTOR.value:
        print(f"{acc.account_id} has role '{acc.role}', not 'doctor'. "
              "Only a doctor account can be verified.", file=sys.stderr)
        return 1

    updated = service.approve_doctor(acc.account_id, approved=not args.revoke,
                                     by="local-operator", reason=args.reason)
    if updated is None:
        print("Update failed.", file=sys.stderr)
        return 1

    state = "VERIFIED" if updated.doctor_verified else "NOT VERIFIED"
    print(f"{updated.account_id} ({mask_mobile(updated.mobile)}) -> {state}")
    print("The doctor sees the change on their next request; no re-login is required, "
          "but the UI refreshes the session on navigation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
