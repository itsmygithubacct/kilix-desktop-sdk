.PHONY: test test-offline

UV ?= uv

test:
	$(UV) run --locked python validate_contract.py --self-test

test-offline:
	$(UV) run --locked --offline python validate_contract.py --self-test
