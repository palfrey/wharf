Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/xenial64"

  config.vm.box_check_update = false
  config.vm.synced_folder ".", "/vagrant", type: 'virtualbox'

  # config.vm.provider "virtualbox" do |vb|
  #   # Display the VirtualBox GUI when booting the machine
  #   vb.gui = true
  #
  #   # Customize the amount of memory on the VM:
  #   vb.memory = "1024"
  # end

  config.vm.provision "shell", privileged: false, inline: <<-SHELL
    set -eux -o pipefail
    sudo apt-get update
    sudo apt-get install --no-install-recommends -y build-essential python python3-pip git apt-transport-https curl redis-server chromium-driver python3-setuptools python3-wheel python3-dev libssl-dev
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
    echo "deb [arch=amd64] https://download.docker.com/linux/ubuntu xenial stable" | sudo tee /etc/apt/sources.list.d/docker.list
    cd /vagrant
    pip3 install -r requirements.txt
  SHELL
end
