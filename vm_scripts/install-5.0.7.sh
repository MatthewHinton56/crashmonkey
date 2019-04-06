#!/bin/bash

cd /tmp

wget https://kernel.ubuntu.com/~kernel-ppa/mainline/v5.0.7/linux-headers-5.0.7-050007_5.0.7-050007.201904052141_all.deb
wget https://kernel.ubuntu.com/~kernel-ppa/mainline/v5.0.7/linux-headers-5.0.7-050007-generic_5.0.7-050007.201904052141_amd64.deb
wget https://kernel.ubuntu.com/~kernel-ppa/mainline/v5.0.7/linux-image-unsigned-5.0.7-050007-generic_5.0.7-050007.201904052141_amd64.deb
wget https://kernel.ubuntu.com/~kernel-ppa/mainline/v5.0.7/linux-modules-5.0.7-050007-generic_5.0.7-050007.201904052141_amd64.deb

sudo dpkg -i *.deb

