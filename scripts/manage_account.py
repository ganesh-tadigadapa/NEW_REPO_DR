#!/usr/bin/env python3
"""Account administration for the prototype: list, inspect, delete.

SAME TRUST BOUNDARY AS scripts/approve_doctor.py
    Running this requires write access to the server's account store, i.e. you are the
    operator of the deployment. It has no network surface, accepts no token, and cannot
    be triggered by any API call, request body or signup form.

WHY THERE IS NO "CHANGE ROLE" COMMAND
    Deliberate. `role` is set once, at account creation, from the signup the person
    actually completed; `doctor_verified` is the only privilege that ever changes, and
    only through service.approve_doctor(). Adding a role-rewrite here would create
    exactly the escalation path the rest of the design exists to prevent.

    To move a number from a user account to a doctor account, DELETE the account and let
    the person sign up again choosing "Doctor Account". That re-runs mobile verification
    and collects the medical registration details, which a silent role flip would skip —
    leaving a "doctor" with no credentials on file and nothing for an administrator to
    check.

USAGE
    scripts/manage_account.py --list
    scripts/manage_account.py --show +919876543210
    scripts/manage_account.py --delete +919876543210
    scripts/manage_account.py --delete +919876543210 --yes     # skip the prompt

WHAT DELETING DOES NOT TOUCH
    Screening data. Scans, evidence and clinician reviews are stored separately and hold
    no account reference by design — the medical record does not depend on who was
    logged in. Deleting an account removes the account row and nothing else.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # noqa: E402
import json  # noqa: E402

from src.auth.models import mask_mobile, normalise_mobile  # noqa: E402
from src.auth.storage import get_auth_store  # noqa: E402


def _rows(store):
    return json.loads((store.dir / "accounts.json").read_text())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list every account")
    ap.add_argument("--show", metavar="MOBILE", help="show one account in full")
    ap.add_argument("--delete", metavar="MOBILE", help="permanently delete one account")
    ap.add_argument("--yes", action="store_true", help="do not prompt for confirmation")
    args = ap.parse_args()

    store = get_auth_store()

    if args.list or not (args.show or args.delete):
        accs = store.list_accounts()
        if not accs:
            print(f"No accounts. (store: {store.dir})")
            return 0
        print(f"{'ACCOUNT ID':<24}{'MOBILE':<20}{'ROLE':<9}{'DOCTOR OK':<11}CREATED")
        for a in accs:
            print(f"{a.account_id:<24}{mask_mobile(a.mobile):<20}{a.role:<9}"
                  f"{str(a.doctor_verified):<11}{a.created_at[:19]}")
        return 0

    target = args.show or args.delete
    try:
        mobile = normalise_mobile(target)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    acc = store.get_by_mobile(mobile)
    if acc is None:
        print(f"No account for {mask_mobile(mobile)}", file=sys.stderr)
        return 1

    if args.show:
        d = acc.to_record()
        d["mobile"] = mask_mobile(d["mobile"])      # never print the full number
        print(json.dumps(d, indent=2))
        return 0

    # ---- delete -------------------------------------------------------------
    print(f"About to permanently delete:")
    print(f"  account   {acc.account_id}")
    print(f"  mobile    {mask_mobile(acc.mobile)}")
    print(f"  role      {acc.role}  (doctor_verified={acc.doctor_verified})")
    print(f"  created   {acc.created_at}")
    print("\nScans, evidence and clinician reviews are NOT affected.")

    if not args.yes:
        try:
            if input("\nType 'delete' to confirm: ").strip().lower() != "delete":
                print("aborted.")
                return 1
        except (EOFError, KeyboardInterrupt):
            print("\naborted.")
            return 1

    rows = [r for r in _rows(store) if r.get("account_id") != acc.account_id]
    (store.dir / "accounts.json").write_text(json.dumps(rows, indent=2))
    store.drop_challenge(mobile)                    # any pending OTP goes too

    print(f"\nDeleted {acc.account_id}.")
    print(f"{mask_mobile(mobile)} can now sign up again and choose an account type.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
