# The Hypervisor

This is a really chrootin proof-of-content hypevisor for Gilliam.
"procs" (applications running inside an somewhat isolated container).

Right now it is not possible to install the beast, so you need do some
hackery to get it working:

First set up your virtualenv and install the requirements.

    $ virtualenv .
    $ bin/pip install -r requirements.txt

Now you can start the hypervisor with this intuitive commandline:

    $ sudo -s
    # . bin/activate
    # export PYTHONPATH=$PWD
    # honcho start -p 9000

Don't forget to set up your template container. 


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

# Template Container using mount --bind

It is also possible to hash the `provision` and `cleanup` scripts (we
should really provide examples of this) to mount the host systems
`/usr` and `/bin` directories using `mount --bind`.  This is a lot
faster than copying a large template installation.  It also saves you
a ton of space. *But* data from the host environment may leak into the
container, plus you there's a risk of wiping the hosts installation if
you manage to do a `rm -rf` on the container without unmounting the
bindings.
