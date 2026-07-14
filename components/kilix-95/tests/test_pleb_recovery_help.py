"""Pleb recovery Help opens the canonical guide with actionable fallback."""
import atexit
import os
import shutil
import tempfile

import harness as H
import shell as shell_mod


root = tempfile.mkdtemp(prefix="kilix95-pleb-recovery-")
atexit.register(shutil.rmtree, root, ignore_errors=True)
installed = os.path.join(root, "installed", "RECOVERY.md")
source_home = os.path.join(root, "sources")
source_doc = os.path.join(source_home, "pleb", "docs", "RECOVERY.md")
override = os.path.join(root, "override", "RECOVERY.md")
for path in (installed, source_doc, override):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write("# Pleb recovery\n")

shell_mod.PLEB_RECOVERY_DOC = installed
os.environ["GPU_TERMINAL_SOURCE_HOME"] = source_home
d = H.make_desk()
opened = []
d.shell.open_app = lambda app, arg=None: opened.append((app, arg))

# A deliberate installer destination override wins when exported at runtime.
os.environ["PLEB_RECOVERY_DOC_DST"] = override
assert d.shell.pleb_recovery_doc_candidates() == [override, installed,
                                                  source_doc]
assert d.shell.open_pleb_recovery() == override
assert opened.pop() == ("notepad", override)

# The stable installed path wins normally; source remains a development
# fallback for a canonical ~/gpu_terminal-style checkout.
os.environ.pop("PLEB_RECOVERY_DOC_DST")
assert d.shell.open_pleb_recovery() == installed
assert opened.pop() == ("notepad", installed)
os.unlink(installed)
assert d.shell.open_pleb_recovery() == source_doc
assert opened.pop() == ("notepad", source_doc)

# Missing documentation never raises or silently does nothing. The dialog
# gives both the complete Plebian-OS dependency refresh and the immediate
# libxxhash package recovery command.
os.unlink(source_doc)
messages = []
old_msgbox = shell_mod.wm.msgbox
shell_mod.wm.msgbox = lambda desk, title, message, **kw: \
    messages.append((title, message, kw))
try:
    assert d.shell.open_pleb_recovery() is None
finally:
    shell_mod.wm.msgbox = old_msgbox
assert len(messages) == 1, messages
title, message, options = messages[0]
assert title == "Pleb Recovery Guide"
assert "/usr/local/sbin/plebian-os-install-deps" in message
assert "sudo apt-get install libxxhash-dev" in message
assert options.get("icon") == "warn"

print("ok")
