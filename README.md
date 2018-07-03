[![FOSSA Status](https://app.fossa.io/api/projects/git%2Bgithub.com%2Fpalfrey%2Fwharf.svg?type=shield)](https://app.fossa.io/projects/git%2Bgithub.com%2Fpalfrey%2Fwharf?ref=badge_shield)

Wharf
=====

Wharf is an opinionated web frontend for [Dokku](http://dokku.viewdocs.io/dokku/). You can also use the command line version, but most features you'll need day-to-day are in the Web UI

Setup
-----
1. [Install Dokku](http://dokku.viewdocs.io/dokku/getting-started/installation)
2. Install the following plugins:
  * https://github.com/dokku/dokku-redis
  * https://github.com/dokku/dokku-postgres
  * https://github.com/dokku/dokku-letsencrypt
3. Setup the Let's Encrypt plugin to auto-renew (`dokku letsencrypt:cron-job --add`)
4. Create the app (`dokku apps:create wharf`)
5. Add SSH key storage:
  * `mkdir /var/lib/dokku/data/storage/wharf-ssh/`
  * `chown dokku:dokku /var/lib/dokku/data/storage/wharf-ssh/`
  * `dokku storage:mount wharf /var/lib/dokku/data/storage/wharf-ssh/:/app/.ssh`
6. Add Redis (`dokku redis:create wharf && dokku redis:link wharf wharf`)
7. Add Postgres (`dokku redis:create wharf && dokku redis:link wharf wharf`)
8. Set `ADMIN_PASSWORD` to something secret (`dokku config:set wharf ADMIN_PASSWORD=somesecret`)
9. Deploy this Git repo [as per the standard Dokku instructions](http://dokku.viewdocs.io/dokku/deployment/application-deployment/)

Helpful hints
-------------
* If there's a Dockerfile in your repository, it'll [try and deploy using that by default](http://dokku.viewdocs.io/dokku/deployment/methods/dockerfiles/). Set BUILDPACK_URL to override
* BUILDPACK_URL should be an HTTPS one, not a SSH or heroku/something one
* You should setup the global domain name when creating Dokku to start with and add a *.&lt;your dokku domain&gt; entry to give new apps more usable names.

Enabling Github auto-deploy webhooks
------------------------------------
1. Set `GITHUB_SECRET` config item to something secret
2. Goto [settings/webhooks](https://developer.github.com/webhooks/creating/#setting-up-a-webhook) in Github
3. Make a new webhook for &lt;your Wharf instance&gt;/webhook with Content type as `application/json` and Secret to the secret from `GITHUB_SECRET`

## License
[![FOSSA Status](https://app.fossa.io/api/projects/git%2Bgithub.com%2Fpalfrey%2Fwharf.svg?type=large)](https://app.fossa.io/projects/git%2Bgithub.com%2Fpalfrey%2Fwharf?ref=badge_large)