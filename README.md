git clone https://github.com/dokku/dokku-daemon
cd dokku-daemon
apt-get install socat
make install
service dokku-daemon start

dokku plugin:install https://github.com/dokku/dokku-redis.git redis
dokku plugin:install https://github.com/dokku/dokku-postgres.git postgres

dokku apps:create dokku-api
dokku redis:create dokku-api
dokku postgres:create dokku-api
dokku redis:link dokku-api dokku-api
dokku postgres:link dokku-api dokku-api
dokku storage:mount dokku-api /var/run/dokku-daemon:/var/run/dokku-daemon
dokku ps:scale dokku-api worker=1 

git clone https://github.com/dokku/dokku-api
cd dokku-api
git remote add dokku ssh://dokku@127.0.0.1:2222/dokku-api
git push dokku master