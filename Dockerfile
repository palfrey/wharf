FROM python:3
WORKDIR /work
COPY requirements.txt /work
RUN pip install -r requirements.txt
CMD ./wait-for-it.sh postgres:5432 --strict --timeout=0 -- bash -c "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"