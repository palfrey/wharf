FROM python:3.6.10
WORKDIR /app
COPY requirements.txt /app/
RUN pip install -r requirements.txt
COPY yarn.lock package.json /app/
RUN curl -sL https://deb.nodesource.com/setup_14.x | bash -
RUN curl -sL https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add -
RUN echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee /etc/apt/sources.list.d/yarn.list
RUN apt-get update
RUN apt-get install -y yarn
RUN yarn install
COPY . /app
RUN python manage.py collectstatic --no-input