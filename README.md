dokku plugin:install https://github.com/dokku/dokku-redis.git
dokku plugin:install https://github.com/dokku/dokku-postgres.git
dokku plugin:install https://github.com/dokku/dokku-letsencrypt.git
dokku letsencrypt:cron-job --add

* If there's a Dockerfile, it'll do that by default (http://dokku.viewdocs.io/dokku/deployment/methods/dockerfiles/). Set BUILDPACK_URL to override
* BUILDPACK_URL should be an HTTPS one, not a SSH or heroku/<foo>
* You should setup the global domain name and add a *.example.com

TODO
* Domains management
* List all task logs
* Auto-deploy from Github
* Restructuring of app config page
* Reformat status messages
* Edit config
* Change name of app
* Lockout non-admins