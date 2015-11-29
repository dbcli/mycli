# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure(2) do |config|

  config.vm.synced_folder ".", "/mycli"

  config.vm.define "debian" do |debian|
    debian.vm.box = "debian/jessie64"
    debian.vm.provision "shell", inline: <<-SHELL
    echo "-> Building DEB"
    sudo apt-get update
    sudo echo "deb http://ppa.launchpad.net/spotify-jyrki/dh-virtualenv/ubuntu trusty main" >> /etc/apt/sources.list
    sudo echo "deb-src http://ppa.launchpad.net/spotify-jyrki/dh-virtualenv/ubuntu trusty main" >> /etc/apt/sources.list
    sudo apt-get update
    sudo apt-get install -y --force-yes python-virtualenv dh-virtualenv debhelper build-essential python-setuptools python-dev
    echo "-> Cleaning up old workspace"
    rm -rf build
    mkdir -p build
    cp -r /mycli build/.
    cd build/mycli

    echo "-> Creating mycli deb"
    dpkg-buildpackage -us -uc
    cp ../*.deb /mycli/.
    SHELL
  end

end

