FROM python:3.12.6
WORKDIR /app
RUN apt-get update && apt-get install -y iproute2
RUN curl -LsSf https://astral.sh/uv/0.13.5/install.sh | sh
RUN uv venv --system-site-packages
COPY pyproject.toml uv.lock /app/
RUN ~/.local/bin/uv sync
COPY . /app
