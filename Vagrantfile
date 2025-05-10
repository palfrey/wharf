Vagrant.configure("2") do |config|
  config.vm.box = "bento/ubuntu-24.04"
  config.vagrant.plugins = "vagrant-libvirt"

  config.vm.box_check_update = false
  config.vm.synced_folder ".", "/vagrant"

  config.vm.network "forwarded_port", guest: 5000, host: 5000

  config.vm.provider :libvirt do |libvirt|
    libvirt.memory = "1024"
    libvirt.machine_type = 'pc-q35-3.1'
  end

  config.vm.provision "shell", privileged: false, inline: <<-SHELL
    set -eux -o pipefail
    sudo apt-get update
    sudo apt-get install --no-install-recommends -y build-essential python3 python3-pip git apt-transport-https curl redis-server firefox python3-setuptools python3-wheel python3-dev libssl-dev xdg-utils hostsed
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
    echo "deb [arch=amd64] https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list
    cd /vagrant
    pip3 install --break-system-packages -r requirements.txt
    ./test.sh
  SHELL
end