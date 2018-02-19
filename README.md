dokku plugin:install https://github.com/dokku/dokku-redis.git redis
dokku plugin:install https://github.com/dokku/dokku-postgres.git postgres
dokku plugin:install https://github.com/dokku/dokku-letsencrypt.git

* If there's a Dockerfile, it'll do that by default (http://dokku.viewdocs.io/dokku/deployment/methods/dockerfiles/). Set BUILDPACK_URL to override
* BUILDPACK_URL should be an HTTPS one, not a SSH or heroku/<foo>