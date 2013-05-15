
# Building a Package

The script `pkg/build-ubuntu-upstart.sh` will build a package for
Ubuntu 12.04 LTS using upstart to launch the service:

     $ pkg/build-ubuntu-upstart.sh

The script will build a virtualenv in `/opt/gilliam/hypervisor` and
replace any scripts to refer to the python executable there.

Things that need to be installed: `fpm`.

