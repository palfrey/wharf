FROM python:3.12.6
WORKDIR /app
RUN apt-get update && apt-get install -y iproute2 netcat-openbsd
COPY requirements.txt /app
RUN pip install -r requirements.txt
COPY . /app
