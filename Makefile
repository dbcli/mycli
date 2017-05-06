.PHONY: clean lint lint-fix test test-all

help:
	@echo "clean - remove all build artifacts"
	@echo "lint - check code changes against PEP 8"
	@echo "lint-fix - automatically fix PEP 8 violations"
	@echo "test - run tests quickly with the current Python"
	@echo "test-all - run tests in all environments"

clean:
	rm -rf build dist egg *.egg-info
	find . -name '*.py[co]' -exec rm -f {} +

lint:
	pep8radius master --docformatter --error-status || ( pep8radius master --docformatter --diff; false )

lint-fix:
	pep8radius master --docformatter --in-place

test:
	if pytest ; then cd test && behave ; fi

test-all:
	tox
