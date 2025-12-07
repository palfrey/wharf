.venv/bin/python:
	uv venv

sync: .venv/bin/python requirements.txt
	uv pip sync --strict requirements.txt

requirements.txt: requirements.in .venv/bin/python
	uv pip compile requirements.in -o requirements.txt --python-version 3.12 --no-strip-extras

watch-test: sync
	.venv/bin/ptw --now --runner .venv/bin/pytest . -vvv

pre-commit: sync
	.venv/bin/pre-commit run -a
