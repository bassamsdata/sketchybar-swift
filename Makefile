.PHONY: check test helpers lint format-check
check:
	python3 plugins/bar.py check
	for file in sketchybarrc install.sh helper/build.sh; do bash -n "$$file" || exit; done
	python3 -m unittest discover -s tests -v

test: check

helpers:
	bash helper/build.sh

lint:
	ruff check plugins tests helper/build.py install.py

format-check:
	ruff format --check plugins tests helper/build.py install.py
