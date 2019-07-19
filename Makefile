pytest_args ?= $(PYTEST_ARGS)
ifdef UPSTREAM
	pytest_args += --tc-file=tests/test-config-upstream.yaml --tc-format=yaml
endif
ifndef UPSTREAM
	pytest_args += --tc-file=tests/test-config.yaml --tc-format=yaml
endif

all: check

check:
	tox

tests:
	pipenv run pytest tests $(pytest_args)

.PHONY: \
	check \
	tests
