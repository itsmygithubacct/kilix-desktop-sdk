# Root gate for the kilix-desktop-sdk monorepo.
#
# The house convention across 0.2.1 repositories is `make check`. This
# repository previously defined it nowhere: an operator or CI following that
# convention got "No rule to make target 'check'", exit 2, which reads as a
# broken build rather than a missing target.
#
# `check` runs the two repository-level verifiers and then every component
# that defines a `test` target. It fails if any of them fails.
#
#   make check            # everything
#   make verify           # repository-level verifiers only
#   make test             # component suites only
#   make check UV=/path/to/uv   # forwarded to components that use it

PYTHON ?= python3
UV ?=
COMPONENTS := $(patsubst components/%/Makefile,%,$(wildcard components/*/Makefile))

.PHONY: check verify test $(COMPONENTS) help

check: verify test

verify:
	@echo "== repository verifiers"
	$(PYTHON) tools/verify-layout.py
	$(PYTHON) tools/verify-provenance.py

test: $(COMPONENTS)

$(COMPONENTS):
	@echo "== components/$@"
	$(MAKE) -C components/$@ test $(if $(UV),UV=$(UV),)

help:
	@echo "targets: check (verify + test), verify, test, $(COMPONENTS)"
