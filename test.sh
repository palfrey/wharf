#!/bin/bash

set -eux -o pipefail

export PYTHONUNBUFFERED=1

if [ -f /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
    sudo systemctl restart nginx
fi

REDIS_URL=redis://dummy python3 manage.py test
wget -nv -O - https://packagecloud.io/dokku/dokku/gpgkey | sudo apt-key add -
if [ ! -f /etc/apt/sources.list.d/dokku.list ]; then
    echo "deb https://packagecloud.io/dokku/dokku/ubuntu/ noble main" | sudo tee /etc/apt/sources.list.d/dokku.list
    sudo apt-get update
fi
echo dokku dokku/skip_key_file boolean true | sudo debconf-set-selections
sudo DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y dokku
sudo dokku plugin:install-dependencies --core
(dokku plugin:list | grep redis) || sudo dokku plugin:install https://github.com/dokku/dokku-redis.git --committish 1.39.3 redis
(dokku plugin:list | grep postgres) || sudo dokku plugin:install https://github.com/dokku/dokku-postgres.git --committish 1.43.0 postgres
(dokku plugin:list | grep letsencrypt) || sudo dokku plugin:install https://github.com/dokku/dokku-letsencrypt.git --committish 0.22.0 letsencrypt
dokku plugin:list
dokku letsencrypt:cron-job --add
(dokku apps:list | grep wharf) || dokku apps:create wharf
(dokku redis:list | grep wharf) || (dokku redis:create wharf && dokku redis:link wharf wharf)
(dokku postgres:list | grep wharf) || (dokku postgres:create wharf && dokku postgres:link wharf wharf)
(git remote | grep dokku) || git remote add dokku ssh://dokku@localhost/wharf
if [ ! -f ~/.ssh/id_rsa ]; then
    yes y | ssh-keygen -t rsa -N '' -f ~/.ssh/id_rsa
fi
(dokku ssh-keys:list | grep travis) || sudo dokku ssh-keys:add travis ~/.ssh/id_rsa.pub
dokku ssh-keys:list
sudo chmod 600 /home/dokku/.ssh/authorized_keys
sudo chmod 700 /home/dokku/.ssh
KEY_DIR=`pwd`/keys
if [ ! -d $KEY_DIR ]; then
    mkdir -p $KEY_DIR
fi
sudo chown dokku:dokku $KEY_DIR
(dokku storage:list wharf | grep ssh) || dokku storage:mount wharf $KEY_DIR:/root/.ssh
GIT_SSH_COMMAND="ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -v" git push dokku HEAD:refs/heads/master
export WHARF_HOSTNAME=wharf.$(hostname --long)
sudo hostsed add 127.0.0.1 $WHARF_HOSTNAME
dokku ps:scale wharf celery=1
sudo docker ps
sudo apt-get install -y net-tools
sudo netstat -nlp
dokku domains:report
dokku proxy:report
dokku ports:report
python3 check_boot.py http://$WHARF_HOSTNAME
if [ ! -f $KEY_DIR/id_rsa ]; then
    echo "Can't find keys in key dir"
    ls $KEY_DIR
    exit 1
fi
