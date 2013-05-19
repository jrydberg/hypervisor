# The Hypervisor

This is a simple hypervisor for Gilliam.  The hypervisor itself is
agnostic to virtualization technique; all that magic is implemented in
a set of shell scripts living in `scripts/`.  The hypervisor comes
with scripts that will start the applications in a LXC container.

[![Build Status](https://travis-ci.org/gilliam/hypervisor.png)](https://travis-ci.org/gilliam/hypervisor)

# Installation

First set up your virtualenv and install the requirements:

    virtualenv .
    bin/pip install -r requirements.txt

Now you can start the hypervisor with this intuitive commandline:

    sudo -s
    . bin/activate
    export PYTHONPATH=$PWD
    honcho start -p 9000

Don't forget to set up your template container. 

# Integration Scripts

TBD.

# Preparing Template Container

The included scripts provide a simple chroot container.  This is a
very simple and naive form of isolation.  But it will do for now, at
least for this prototype.

First we need to create a "template" for the containers.  We do this
with `debootstrap`.  Follow these steps:

    $ sudo mkdir -p /var/lib/gilliam/template
    $ sudo apt-get install debootstrap
    ...
    $ sudo debootstrap --variant buildd --arch amd64 precise /var/lib/gilliam/template
    ...
    I: Base system installed successfully.
    $

If debootstrap finishes successfully, you'll be left with a base
chroot directory, which is not suitable for nearly anything. To
actually get our chroot to work and be able to host applications we
need to do a few more things:

    $ sudo cp /etc/resolv.conf /var/lib/gilliam/template/etc/resolv.conf
    $ sudo cp /etc/apt/sources.list /var/lib/gilliam/template/etc/apt/
    $ sudo chroot /var/lib/gilliam/template
    # useradd -d /app gilliam

Depending on what you expect to run in the container you need some
extra packages.  For python, which is my main environment, you'll have
to install these:

    (inside the jail)
    # apt-get update
    # apt-get install libssl0.9.8 ...

All done.

The `provision` script will take care of mounting `/proc` and other key
file systems.
