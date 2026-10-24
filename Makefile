.venv/bin/python:
	uv venv

sync: .venv/bin/python pyproject.toml
	uv sync

watch-test: sync
	.venv/bin/ptw --now --runner .venv/bin/pytest . -vvv

pre-commit: sync
	.venv/bin/pre-commit run -a
