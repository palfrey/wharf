Vagrant.configure("2") do |config|
  config.vm.box = "debian/stretch64"

  config.vm.box_check_update = false
  config.vm.synced_folder ".", "/vagrant", type: 'virtualbox'

  # config.vm.provider "virtualbox" do |vb|
  #   # Display the VirtualBox GUI when booting the machine
  #   vb.gui = true
  #
  #   # Customize the amount of memory on the VM:
  #   vb.memory = "1024"
  # end

  config.vm.provision "shell", inline: <<-SHELL
    sudo apt-get install -y python3-pip git apt-transport-https curl redis-server chromium-driver
    curl -fsSL https://download.docker.com/linux/debian/gpg | sudo apt-key add -
    echo "deb [arch=amd64] https://download.docker.com/linux/debian stretch stable" | sudo tee /etc/apt/sources.list.d/docker.list
    pip3 install -r requirements.txt
    CHROMEDRIVER_PATH=/usr/bin/chromedriver ./test.sh
  SHELL
end
