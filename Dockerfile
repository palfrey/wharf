FROM python:3
WORKDIR /work
COPY requirements.txt /work
RUN pip install -r requirements.txt