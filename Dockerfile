FROM python:3.6.10
WORKDIR /app
RUN curl -sL https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add -
RUN echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee /etc/apt/sources.list.d/yarn.list
RUN curl -sL https://deb.nodesource.com/setup_14.x | bash -
RUN apt-get install -y yarn
COPY requirements.txt yarn.lock package.json /app/
RUN pip install -r requirements.txt
RUN yarn install
COPY . /app
RUN REDIS_URL=ignore python manage.py collectstatic --no-input