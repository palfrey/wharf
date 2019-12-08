#!/bin/bash
set -eux -o pipefail

python manage.py migrate
python manage.py runserver 0.0.0.0:${PORT:-5000}