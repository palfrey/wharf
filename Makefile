.venv/bin/python:
	uv venv

sync: .venv/bin/python requirements.txt
	uv pip sync requirements.txt

requirements.txt: requirements.in .venv/bin/python
	uv pip compile requirements.in -o requirements.txt --python-version 3.12 --no-strip-extras