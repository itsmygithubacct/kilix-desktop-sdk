"""Default-password nag: talk to the Plebian-OS `plebian-os-passwd` helper.

Plebian-OS ships the account with a default password ('plebian') and installs a
tiny root helper plus a narrow passwordless-sudo rule so this desktop — running
as the unprivileged owner — can (a) tell whether the login password is still
that default and (b) change it, without any general passwordless sudo. On a
plain kilix-95 checkout (no helper) every call is a graceful no-op, so the nag
simply never appears.
"""
import os
import shutil
import subprocess

HELPER = "/usr/local/sbin/plebian-os-passwd"


def available():
    return bool(shutil.which("sudo")) and os.access(HELPER, os.X_OK)


def is_default_password():
    """True only when we can CONFIRM the login password is still 'plebian'.
    Any uncertainty (no helper, no sudo rule, timeout, error) → False, so the
    nag never shows spuriously."""
    if not available():
        return False
    try:
        r = subprocess.run(["sudo", "-n", HELPER, "check"],
                           stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def change_password(newpw):
    """Set the login password to `newpw`. Returns (ok, message)."""
    if not available():
        return False, "The password helper is not available on this system."
    try:
        r = subprocess.run(["sudo", "-n", HELPER, "set"],
                           input=(newpw + "\n"), text=True,
                           capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"Could not run the password helper: {e}"
    if r.returncode == 0:
        return True, "Your password has been changed."
    msg = (r.stderr or r.stdout or "").strip()
    # strip the helper's own prefix for a friendlier dialog message
    msg = msg.replace("plebian-os-passwd: ", "")
    return False, msg or "The password could not be changed."
