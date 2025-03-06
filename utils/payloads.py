import base64
import json
import os
import random
import uuid
from datetime import datetime
from datetime import timedelta
from datetime import timezone

# complete system identity
# IDENTITY = {
#    "org_id": "test",
#    "type": "System",
#    "auth_type": "cert-auth",
#    "system": {"cn": "1b36b20f-7fa0-4454-a6d2-008294e06378", "cert_type": "system"},
#    "internal": {"auth_time": 6300},
# }

# system identity: invalid or incomplete for testing
# IDENTITY = {
#     "org_id": "sysorgid",
#     "type": "System",
#     "auth_type": "invalid-auth",
#     "system": {"cn": "1b36b20f-7fa0-4454-a6d2-008294e06378", "cert_type": "system"},
#     "internal": {"auth_time": 6300},
# }

# complete user identity
IDENTITY = {
    "org_id": "test",
    "type": "User",
    "auth_type": "basic-auth",
    "user": {"email": "jramos@redhat.com", "first_name": "test"},
}

# incomplete or invalid user identity for testing
# IDENTITY = {
#     "org_id": "test",
#     "type": "User",
#     "auth_type": "basic-auth",
# }


apiKey = base64.b64encode(json.dumps({"identity": IDENTITY}).encode("utf-8"))


def rpm_list():
    return [
        "rpm-python-4.11.3-32.el7.x86_64",
        "redhat-release-server-7.5-8.el7.x86_64",
        "gpgme-1.3.2-5.el7.x86_64",
        "setup-2.8.71-9.el7.noarch",
        "yum-3.4.3-158.el7.noarch",
        "tzdata-2018c-1.el7.noarch",
        "rhn-setup-2.0.2-21.el7.noarch",
        "grub2-pc-modules-2.02-0.65.el7_4.2.noarch",
        "rhn-check-2.0.2-21.el7.noarch",
        "nss-softokn-freebl-3.34.0-2.el7.x86_64",
        "firewalld-filesystem-0.4.4.4-14.el7.noarch",
        "glibc-2.17-222.el7.x86_64",
        "bind-libs-lite-9.9.4-61.el7.x86_64",
        "nss-util-3.34.0-2.el7.x86_64",
        "dracut-network-033-535.el7.x86_64",
        "ncurses-libs-5.9-14.20130511.el7_4.x86_64",
        "subscription-manager-rhsm-1.20.10-1.el7.x86_64",
        "libsepol-2.5-8.1.el7.x86_64",
        "emacs-filesystem-24.3-20.el7_4.noarch",
        "libselinux-2.5-12.el7.x86_64",
        "xdg-utils-1.1.0-0.17.20120809git.el7.noarch",
        "info-5.1-5.el7.x86_64",
        "kbd-1.15.5-13.el7.x86_64",
        "libcom_err-1.42.9-11.el7.x86_64",
        "subscription-manager-1.20.10-1.el7.x86_64",
        "sed-4.2.2-5.el7.x86_64",
        "firewalld-0.4.4.4-14.el7.noarch",
        "chkconfig-1.7.4-1.el7.x86_64",
        "postfix-2.10.1-6.el7.x86_64",
        "bzip2-libs-1.0.6-13.el7.x86_64",
        "NetworkManager-team-1.10.2-13.el7.x86_64",
        "readline-6.2-10.el7.x86_64",
        "lvm2-2.02.177-4.el7.x86_64",
        "gawk-4.0.2-4.el7_3.1.x86_64",
        "grub2-2.02-0.65.el7_4.2.x86_64",
        "libgpg-error-1.12-3.el7.x86_64",
        "openssh-clients-7.4p1-16.el7.x86_64",
        "libgcrypt-1.5.3-14.el7.x86_64",
        "lshw-B.02.18-12.el7.x86_64",
        "libcap-2.22-9.el7.x86_64",
        "kernel-3.10.0-862.el7.x86_64",
        "libcap-ng-0.7.5-4.el7.x86_64",
        "microcode_ctl-2.1-29.el7.x86_64",
        "which-2.20-7.el7.x86_64",
        "qemu-guest-agent-2.8.0-2.el7.x86_64",
        "libnl3-3.2.28-4.el7.x86_64",
        "chrony-3.2-2.el7.x86_64",
        "sqlite-3.7.17-8.el7.x86_64",
        "parted-3.1-29.el7.x86_64",
        "findutils-4.5.11-5.el7.x86_64",
        "sudo-1.8.19p2-13.el7.x86_64",
        "file-libs-5.11-33.el7.x86_64",
        "btrfs-progs-4.9.1-1.el7.x86_64",
        "libmnl-1.0.3-7.el7.x86_64",
        "e2fsprogs-1.42.9-11.el7.x86_64",
        "libnl3-cli-3.2.28-4.el7.x86_64",
        "kernel-tools-3.10.0-862.el7.x86_64",
        "libassuan-2.1.0-3.el7.x86_64",
        "libsysfs-2.1.0-16.el7.x86_64",
        "e2fsprogs-libs-1.42.9-11.el7.x86_64",
        "iwl135-firmware-18.168.6.1-62.el7.noarch",
        "libunistring-0.9.3-9.el7.x86_64",
        "iwl5000-firmware-8.83.5.1_1-62.el7.noarch",
        "libgomp-4.8.5-28.el7.x86_64",
        "iwl2030-firmware-18.168.6.1-62.el7.noarch",
        "libnfnetlink-1.0.1-4.el7.x86_64",
        "ivtv-firmware-20080701-26.el7.noarch",
        "sysvinit-tools-2.88-14.dsf.el7.x86_64",
        "iwl100-firmware-39.31.5.1-62.el7.noarch",
        "newt-0.52.15-4.el7.x86_64",
        "iwl6000g2a-firmware-17.168.5.3-62.el7.noarch",
        "lz4-1.7.5-2.el7.x86_64",
        "rootfiles-8.1-11.el7.noarch",
        "tcp_wrappers-libs-7.6-77.el7.x86_64",
        "iwl1000-firmware-39.31.5.1-62.el7.noarch",
        "hostname-3.13-3.el7.x86_64",
        "iwl4965-firmware-228.61.2.24-62.el7.noarch",
        "keyutils-libs-1.5.8-3.el7.x86_64",
        "iwl5150-firmware-8.24.2.2-62.el7.noarch",
        "iptables-1.4.21-24.el7.x86_64",
        "gpg-pubkey-2fa658e0-45700c69",
        "less-458-9.el7.x86_64",
        "pciutils-3.5.1-3.el7.x86_64",
        "ipset-libs-6.29-1.el7.x86_64",
        "python-backports-1.0-8.el7.x86_64",
        "acl-2.2.51-14.el7.x86_64",
        "python-urllib3-1.10.2-5.el7.noarch",
        "tar-1.26-34.el7.x86_64",
        "python-setuptools-0.9.8-7.el7.noarch",
        "libdb-utils-5.3.21-24.el7.x86_64",
        "libyaml-0.1.4-11.el7_0.x86_64",
        "libss-1.42.9-11.el7.x86_64",
        "insights-client-3.0.3-9.el7_5.noarch",
        "make-3.82-23.el7.x86_64",
        "kernel-3.10.0-862.3.2.el7.x86_64",
        "libselinux-utils-2.5-12.el7.x86_64",
        "dhcp-common-4.2.5-68.el7_5.1.x86_64",
        "ncurses-5.9-14.20130511.el7_4.x86_64",
        "ruby-libs-2.0.0.648-34.el7_6.x86_64",
        "mozjs17-17.0.0-20.el7.x86_64",
        "rubygem-json-1.7.7-34.el7_6.x86_64",
        "libfastjson-0.99.4-2.el7.x86_64",
        "ruby-irb-2.0.0.648-34.el7_6.noarch",
        "libnl-1.1.4-3.el7.x86_64",
        "rubygem-io-console-0.4.2-34.el7_6.x86_64",
        "kernel-tools-libs-3.10.0-862.el7.x86_64",
        "rubygem-rdoc-4.0.0-34.el7_6.noarch",
        "libseccomp-2.3.1-3.el7.x86_64",
        "qrencode-libs-3.4.1-3.el7.x86_64",
        "ustr-1.0.4-16.el7.x86_64",
        "libestr-0.1.9-2.el7.x86_64",
        "lsscsi-0.27-6.el7.x86_64",
        "device-mapper-persistent-data-0.7.3-3.el7.x86_64",
        "numactl-libs-2.0.9-7.el7.x86_64",
        "p11-kit-trust-0.23.5-3.el7.x86_64",
        "openssl-libs-1.0.2k-12.el7.x86_64",
        "krb5-libs-1.15.1-18.el7.x86_64",
        "python-2.7.5-68.el7.x86_64",
        "shadow-utils-4.1.5.1-24.el7.x86_64",
        "python-decorator-3.4.0-3.el7.noarch",
        "python-iniparse-0.4-9.el7.noarch",
        "libmount-2.23.2-52.el7.x86_64",
        "shared-mime-info-1.8-4.el7.x86_64",
        "gobject-introspection-1.50.0-1.el7.x86_64",
        "libcroco-0.6.11-1.el7.x86_64",
        "libpwquality-1.2.3-5.el7.x86_64",
        "python-lxml-3.2.1-4.el7.x86_64",
        "python-six-1.9.0-2.el7.noarch",
        "cyrus-sasl-lib-2.1.26-23.el7.x86_64",
        "gettext-0.19.8.1-2.el7.x86_64",
        "pygobject2-2.28.6-11.el7.x86_64",
        "libutempter-1.1.6-4.el7.x86_64",
        "libselinux-python-2.5-12.el7.x86_64",
        "pyliblzma-0.5.3-11.el7.x86_64",
        "pyOpenSSL-0.13.1-3.el7.x86_64",
        "python-schedutils-0.4-6.el7.x86_64",
        "python-configobj-4.7.2-7.el7.noarch",
        "libxml2-python-2.9.1-6.el7_2.3.x86_64",
        "python-magic-5.11-33.el7.noarch",
        "openssl-1.0.2k-12.el7.x86_64",
        "nss-3.34.0-4.el7.x86_64",
        "nss-tools-3.34.0-4.el7.x86_64",
        "logrotate-3.8.6-15.el7.x86_64",
        "alsa-lib-1.1.4.1-2.el7.x86_64",
        "fipscheck-1.4.1-6.el7.x86_64",
        "libssh2-1.4.3-10.el7_2.1.x86_64",
        "curl-7.29.0-46.el7.x86_64",
        "rpm-4.11.3-32.el7.x86_64",
        "libuser-0.60-9.el7.x86_64",
        "kpartx-0.4.9-119.el7.x86_64",
        "util-linux-2.23.2-52.el7.x86_64",
        "kmod-20-21.el7.x86_64",
        "cryptsetup-libs-1.7.4-4.el7.x86_64",
        "systemd-libs-219-57.el7.x86_64",
        "systemd-219-57.el7.x86_64",
        "elfutils-default-yama-scope-0.170-4.el7.noarch",
        "polkit-pkla-compat-0.1-4.el7.x86_64",
        "initscripts-9.49.41-1.el7.x86_64",
        "hwdata-0.252-8.8.el7.x86_64",
        "grub2-tools-minimal-2.02-0.65.el7_4.2.x86_64",
        "cronie-anacron-1.4.11-19.el7.x86_64",
        "crontabs-1.11-6.20121102git.el7.noarch",
        "grub2-tools-2.02-0.65.el7_4.2.x86_64",
        "openssh-7.4p1-16.el7.x86_64",
        "grub2-tools-extra-2.02-0.65.el7_4.2.x86_64",
        "selinux-policy-3.13.1-192.el7.noarch",
        "lvm2-libs-2.02.177-4.el7.x86_64",
        "libdrm-2.4.83-2.el7.x86_64",
        "wpa_supplicant-2.6-9.el7.x86_64",
        "ebtables-2.0.10-16.el7.x86_64",
        "alsa-firmware-1.0.28-2.el7.noarch",
        "teamd-1.27-4.el7.x86_64",
        "dbus-python-1.1.1-9.el7.x86_64",
        "python-firewall-0.4.4.4-14.el7.noarch",
        "plymouth-core-libs-0.8.9-0.31.20140113.el7.x86_64",
        "plymouth-0.8.9-0.31.20140113.el7.x86_64",
        "python-gudev-147.2-7.el7.x86_64",
        "usermode-1.111-5.el7.x86_64",
        "python-urlgrabber-3.10-8.el7.noarch",
        "pth-2.0.7-23.el7.x86_64",
        "rpm-build-libs-4.11.3-32.el7.x86_64",
        "libgcc-4.8.5-28.el7.x86_64",
        "redhat-support-lib-python-0.9.7-6.el7.noarch",
        "grub2-common-2.02-0.65.el7_4.2.noarch",
        "pygpgme-0.3-9.el7.x86_64",
        "filesystem-3.2-25.el7.x86_64",
        "rhn-client-tools-2.0.2-21.el7.noarch",
        "basesystem-10.0-7.el7.noarch",
        "yum-rhn-plugin-2.0.1-10.el7.noarch",
        "ncurses-base-5.9-14.20130511.el7_4.noarch",
        "rhnsd-5.0.13-10.el7.x86_64",
        "glibc-common-2.17-222.el7.x86_64",
        "bind-license-9.9.4-61.el7.noarch",
        "nspr-4.17.0-1.el7.x86_64",
        "libstdc++-4.8.5-28.el7.x86_64",
        "subscription-manager-rhsm-certificates-1.20.10-1.el7.x86_64",
        "bash-4.2.46-30.el7.x86_64",
        "kbd-misc-1.15.5-13.el7.noarch",
        "pcre-8.32-17.el7.x86_64",
        "desktop-file-utils-0.23-1.el7.x86_64",
        "zlib-1.2.7-17.el7.x86_64",
        "kbd-legacy-1.15.5-13.el7.noarch",
        "xz-libs-5.2.2-1.el7.x86_64",
        "Red_Hat_Enterprise_Linux-Release_Notes-7-en-US-7-2.el7.noarch",
        "libuuid-2.23.2-52.el7.x86_64",
        "kexec-tools-2.0.15-13.el7.x86_64",
        "popt-1.13-16.el7.x86_64",
        "redhat-support-tool-0.9.10-1.el7.noarch",
        "libxml2-2.9.1-6.el7_2.3.x86_64",
        "tuned-2.9.0-1.el7.noarch",
        "libdb-5.3.21-24.el7.x86_64",
        "NetworkManager-tui-1.10.2-13.el7.x86_64",
        "grep-2.20-3.el7.x86_64",
        "selinux-policy-targeted-3.13.1-192.el7.noarch",
        "elfutils-libelf-0.170-4.el7.x86_64",
        "openssh-server-7.4p1-16.el7.x86_64",
        "libffi-3.0.13-18.el7.x86_64",
        "authconfig-6.2.8-30.el7.x86_64",
        "libattr-2.4.46-13.el7.x86_64",
        "audit-2.8.1-3.el7.x86_64",
        "libacl-2.2.51-14.el7.x86_64",
        "irqbalance-1.0.7-11.el7.x86_64",
        "audit-libs-2.8.1-3.el7.x86_64",
        "aic94xx-firmware-30-6.el7.noarch",
        "cpio-2.11-27.el7.x86_64",
        "rsyslog-8.24.0-16.el7.x86_64",
        "expat-2.1.0-10.el7_3.x86_64",
        "biosdevname-0.7.3-1.el7.x86_64",
        "lua-5.1.4-15.el7.x86_64",
        "dracut-config-rescue-033-535.el7.x86_64",
        "diffutils-3.3-4.el7.x86_64",
        "man-db-2.6.3-9.el7.x86_64",
        "file-5.11-33.el7.x86_64",
        "xfsprogs-4.5.0-15.el7.x86_64",
        "nss-softokn-3.34.0-2.el7.x86_64",
        "iprutils-2.4.15.1-1.el7.x86_64",
        "p11-kit-0.23.5-3.el7.x86_64",
        "sg3_utils-1.37-12.el7.x86_64",
        "groff-base-1.22.2-8.el7.x86_64",
        "iwl2000-firmware-18.168.6.1-62.el7.noarch",
        "xz-5.2.2-1.el7.x86_64",
        "iwl3945-firmware-15.32.2.9-62.el7.noarch",
        "libidn-1.28-4.el7.x86_64",
        "iwl105-firmware-18.168.6.1-62.el7.noarch",
        "libedit-3.0-12.20121213cvs.el7.x86_64",
        "iwl7260-firmware-22.0.7.0-62.el7.noarch",
        "lzo-2.06-8.el7.x86_64",
        "iwl6050-firmware-41.28.5.1-62.el7.noarch",
        "slang-2.2.4-11.el7.x86_64",
        "iwl3160-firmware-22.0.7.0-62.el7.noarch",
        "ethtool-4.8-7.el7.x86_64",
        "NetworkManager-config-server-1.10.2-13.el7.noarch",
        "jansson-2.10-1.el7.x86_64",
        "iwl7265-firmware-22.0.7.0-62.el7.noarch",
        "gdbm-1.10-8.el7.x86_64",
        "iwl6000-firmware-9.221.4.1-62.el7.noarch",
        "pciutils-libs-3.5.1-3.el7.x86_64",
        "iwl6000g2b-firmware-17.168.5.2-62.el7.noarch",
        "libnetfilter_conntrack-1.0.6-1.el7_3.x86_64",
        "gpg-pubkey-fd431d51-4ae0493b",
        "iproute-4.11.0-14.el7.x86_64",
        "python-ipaddress-1.0.16-2.el7.noarch",
        "libteam-1.27-4.el7.x86_64",
        "python-chardet-2.2.1-1.el7_1.noarch",
        "ipset-6.29-1.el7.x86_64",
        "python-backports-ssl_match_hostname-3.5.0.1-1.el7.noarch",
        "vim-minimal-7.4.160-4.el7.x86_64",
        "python-requests-2.6.0-1.el7_1.noarch",
        "libxslt-1.1.28-5.el7.x86_64",
        "libcgroup-0.41-15.el7.x86_64",
        "pinentry-0.8.1-17.el7.x86_64",
        "PyYAML-3.10-11.el7.x86_64",
        "kmod-libs-20-21.el7.x86_64",
        "nano-2.3.1-10.el7.x86_64",
        "GeoIP-1.5.0-11.el7.x86_64",
        "dhcp-libs-4.2.5-68.el7_5.1.x86_64",
        "freetype-2.4.11-15.el7.x86_64",
        "dhclient-4.2.5-68.el7_5.1.x86_64",
        "gmp-6.0.0-15.el7.x86_64",
        "rubygem-psych-2.0.0-34.el7_6.x86_64",
        "snappy-1.1.0-3.el7.x86_64",
        "ruby-2.0.0.648-34.el7_6.x86_64",
        "hardlink-1.0-19.el7.x86_64",
        "rubygem-bigdecimal-1.2.0-34.el7_6.x86_64",
        "sg3_utils-libs-1.37-12.el7.x86_64",
        "rubygems-2.0.14.1-34.el7_6.noarch",
        "libndp-1.2-7.el7.x86_64",
        "libdaemon-0.14-7.el7.x86_64",
        "libpipeline-1.2.3-3.el7.x86_64",
        "libsemanage-2.5-11.el7.x86_64",
        "libverto-0.2.5-4.el7.x86_64",
        "libaio-0.3.109-13.el7.x86_64",
        "dmidecode-3.0-5.el7.x86_64",
        "libtasn1-4.10-1.el7.x86_64",
        "ca-certificates-2017.2.20-71.el7.noarch",
        "coreutils-8.22-21.el7.x86_64",
        "python-libs-2.7.5-68.el7.x86_64",
        "libblkid-2.23.2-52.el7.x86_64",
        "gzip-1.5-10.el7.x86_64",
        "python-dateutil-1.5-7.el7.noarch",
        "cracklib-2.9.0-11.el7.x86_64",
        "glib2-2.54.2-2.el7.x86_64",
        "newt-python-0.52.15-4.el7.x86_64",
        "python-gobject-base-3.22.0-1.el7_4.1.x86_64",
        "cracklib-dicts-2.9.0-11.el7.x86_64",
        "pam-1.1.8-22.el7.x86_64",
        "m2crypto-0.21.1-17.el7.x86_64",
        "python-ethtool-0.8-5.el7.x86_64",
        "gettext-libs-0.19.8.1-2.el7.x86_64",
        "pkgconfig-0.27.1-4.el7.x86_64",
        "yum-metadata-parser-1.1.4-10.el7.x86_64",
        "grubby-8.28-23.el7.x86_64",
        "python-slip-0.4.0-4.el7.noarch",
        "python-linux-procfs-0.4.9-3.el7.noarch",
        "rhnlib-2.5.65-7.el7.noarch",
        "python-perf-3.10.0-862.el7.x86_64",
        "python-inotify-0.9.4-4.el7.noarch",
        "python-dmidecode-3.12.2-2.el7.x86_64",
        "pyxattr-0.5.1-5.el7.x86_64",
        "nss-pem-1.0.3-4.el7.x86_64",
        "nss-sysinit-3.34.0-4.el7.x86_64",
        "linux-firmware-20180220-62.git6d51311.el7.noarch",
        "binutils-2.27-27.base.el7.x86_64",
        "redhat-logos-70.0.3-6.el7.noarch",
        "fipscheck-lib-1.4.1-6.el7.x86_64",
        "libcurl-7.29.0-46.el7.x86_64",
        "rpm-libs-4.11.3-32.el7.x86_64",
        "openldap-2.4.44-13.el7.x86_64",
        "procps-ng-3.3.10-17.el7.x86_64",
        "device-mapper-1.02.146-4.el7.x86_64",
        "dracut-033-535.el7.x86_64",
        "device-mapper-libs-1.02.146-4.el7.x86_64",
        "elfutils-libs-0.170-4.el7.x86_64",
        "dbus-libs-1.10.24-7.el7.x86_64",
        "dbus-1.10.24-7.el7.x86_64",
        "polkit-0.112-14.el7.x86_64",
        "iputils-20160308-10.el7.x86_64",
        "systemd-sysv-219-57.el7.x86_64",
        "device-mapper-event-libs-1.02.146-4.el7.x86_64",
        "policycoreutils-2.5-22.el7.x86_64",
        "cronie-1.4.11-19.el7.x86_64",
        "os-prober-1.58-9.el7.x86_64",
        "NetworkManager-libnm-1.10.2-13.el7.x86_64",
        "virt-what-1.18-4.el7.x86_64",
        "grub2-pc-2.02-0.65.el7_4.2.x86_64",
        "device-mapper-event-1.02.146-4.el7.x86_64",
        "libpciaccess-0.14-1.el7.x86_64",
        "python-hwdata-1.7.3-4.el7.noarch",
        "NetworkManager-1.10.2-13.el7.x86_64",
        "fxload-2002_04_11-16.el7.x86_64",
        "alsa-tools-firmware-1.1.0-1.el7.x86_64",
        "dbus-glib-0.100-7.el7.x86_64",
        "python-slip-dbus-0.4.0-4.el7.noarch",
        "python-pyudev-0.15-9.el7.noarch",
        "plymouth-scripts-0.8.9-0.31.20140113.el7.x86_64",
        "libgudev1-219-57.el7.x86_64",
        "passwd-0.79-4.el7.x86_64",
        "python-pycurl-7.19.0-19.el7.x86_64",
        "mariadb-libs-5.5.56-2.el7.x86_64",
        "gnupg2-2.0.22-4.el7.x86_64",
    ]


def create_system_profile():
    return {
        "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        "rhc_client_id": "044e36dc-4e2b-4e69-8948-9c65a7bf4976",
        "rhc_config_state": "044e36dc-4e2b-4e69-8948-9c65a7bf4976",
        "cpu_model": "Intel(R) Xeon(R) CPU E5-2690 0 @ 2.90GHz",
        "number_of_cpus": 1,
        "number_of_sockets": 2,
        "cores_per_socket": 4,
        "system_memory_bytes": 1024,
        "infrastructure_type": "jingleheimer junction cpu",
        "infrastructure_vendor": "dell",
        "network_interfaces": [
            {
                "ipv4_addresses": ["10.10.10.1"],
                "state": "UP",
                "ipv6_addresses": ["2001:0db8:85a3:0000:0000:8a2e:0370:7334"],
                "mtu": 1500,
                "mac_address": "aa:bb:cc:dd:ee:ff",
                "type": "loopback",
                "name": "eth0",
            }
        ],
        "disk_devices": [
            {
                "device": "/dev/sdb1",
                "label": "home drive",
                "options": {"uid": "0", "ro": True},
                "mount_point": "/home",
                "type": "ext3",
            }
        ],
        "bios_vendor": "Turd Ferguson",
        "bios_version": "1.0.0uhoh",
        "bios_release_date": "10/31/2013",
        "cpu_flags": ["flag1", "flag2"],
        "os_release": "Red Hat EL 7.0.1",
        "os_kernel_version": "3.10.0",
        "arch": "x86-64",
        "last_boot_time": "2020-02-13T12:08:55Z",
        "kernel_modules": ["i915", "e1000e"],
        "running_processes": ["vim", "gcc", "python"],
        "subscription_status": "valid",
        "subscription_auto_attach": "yes",
        "katello_agent_running": False,
        "satellite_managed": False,
        "is_marketplace": False,
        "yum_repos": [{"name": "repo1", "gpgcheck": True, "enabled": True, "base_url": "http://rpms.redhat.com"}],
        "installed_products": [
            {"name": "eap", "id": "123", "status": "UP"},
            {"name": "jbws", "id": "321", "status": "DOWN"},
        ],
        "insights_client_version": "12.0.12",
        "insights_egg_version": "120.0.1",
        "captured_date": "2020-02-13T12:16:00Z",
        # "installed_packages": ["rpm1", "rpm2"],
        # "installed_packages": subprocess.getoutput("rpm -qa").split("\n"),
        # "installed_packages": rpm_list(),
        "installed_services": ["ndb", "krb5"],
        "enabled_services": ["ndb", "krb5"],
        "selinux_current_mode": "enforcing",
        "selinux_config_file": "enforcing",
        "operating_system": {"name": "RHEL", "major": 8, "minor": 1},
        "system_update_method": "yum",  # "dnf, rpm-ostree, yum"
    }


def build_rhsm_payload():
    return {
        "org_id": "rhsorgid",
        "bios_uuid": "e56890e3-9ce5-4fb2-b677-3d84e3e4d4a9",
        "facts": [
            {
                "facts": {
                    "ARCHITECTURE": "x86_64",
                    "CPU_CORES": 4,
                    "CPU_SOCKETS": 4,
                    "IS_VIRTUAL": True,
                    "MEMORY": 8,
                    "RH_PROD": ["69", "408", "290"],
                    "SYNC_TIMESTAMP": "2019-08-08T16:32:40.355-04:00",
                    "orgId": "5389686",
                },
                "namespace": "rhsm",
            }
        ],
        "fqdn": "node01.ose.skunkfu.org",
        "ip_addresses": [
            "fe80::46:6bff:fe06:c0f0",
            "10.129.0.1",
            "172.16.10.118",
            "172.17.0.1",
            "fe80::a443:aa45:96ff:2f00",
            "127.0.0.1",
        ],
        "mac_addresses": [
            "5A:3D:18:47:EB:44",
            "02:42:B0:F1:FD:01",
            "52:54:00:CD:65:84",
            "BE:FE:93:D1:A8:20",
            "02:46:6B:06:C0:F0",
            "D6:58:86:AA:AA:40",
        ],
        "subscription_manager_id": "77ecf4c6-ab06-405c-844c-d815973de7f2",
        "reporter": "rhsm-conduit",
        "system_profile": create_system_profile(),
    }


def build_qpc_payload():
    return {
        "display_name": "dhcp-8-29-119.lab.eng.rdu2.redhat.com",
        "bios_uuid": "7E681E42-FCBE-2831-E9E2-78983C7FA869",
        "ip_addresses": ["10.8.29.119"],
        "mac_addresses": ["00:50:56:9e:bb:eb"],
        "insights_id": "137c9d58-941c-4bb9-9426-7879a367c23b",
        "subscription_manager_id": "7E681E42-FCBE-2831-E9E2-78983C7FA869",
        "fqdn": "dhcp-8-29-119.lab.eng.rdu2.redhat.com",
        "facts": [
            {
                "namespace": "qpc",
                "facts": {
                    "rh_product_certs": [],
                    "rh_products_installed": ["RHEL", "EAP", "DCSM", "JWS", "FUSE"],
                    "last_reported": "2019-08-08T15:22:38.345587",
                    "source_types": ["network"],
                },
            }
        ],
        "system_profile": {
            "infrastructure_type": "virtualized",
            "arch": "x86_64",
            "os_release": "Red Hat Enterprise Linux Server release 7.5 (Maipo)",
            "os_kernel_version": "3.10.0",
            "number_of_cpus": 2,
            "number_of_sockets": 2,
            "cores_per_socket": 1,
        },
        "reporter": "yupana",
    }


def random_uuid():
    return str(uuid.uuid4())


IS_EDGE = os.environ.get("IS_EDGE", False)
USE_RANDOMNESS = os.environ.get("USE_RANDOMENESS", True)


def build_host_chunk():
    org_id = os.environ.get("INVENTORY_HOST_ACCOUNT", IDENTITY["org_id"])
    fqdn = random_uuid()[:6] + ".foo.redhat.com"
    system_profile = create_system_profile()

    if IS_EDGE:
        system_profile["host_type"] = "edge"

    payload = {
        "insights_id": random_uuid(),
        "org_id": org_id,
        "display_name": fqdn,
        "tags": [
            {"namespace": "SPECIAL", "key": "key", "value": "val"},
            {"namespace": "NS3", "key": "key3", "value": "val3"},
            {"namespace": "NS1", "key": "key3", "value": "val3"},
            {"namespace": "Sat", "key": "prod", "value": None},
        ],
        "system_profile": system_profile,
        "stale_timestamp": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "reporter": "puptoo",
    }

    # randomize the use of canonical_facts and reporters
    if USE_RANDOMNESS:
        add_bios = random.choice([True, False])
        add_subsman = random.choice([True, False])
        add_provider_id = random.choice([True, False])

        if add_bios:
            payload["bios_uuid"] = random_uuid()

        if add_subsman:
            payload["subscription_manager_id"] = random_uuid()

        if add_provider_id:
            payload["provider_id"] = random_uuid()
            payload["provider_type"] = random.choice(["aws", "azure", "google", "ibm"])

        payload["reporter"] = random.choice(
            ["cloud-connector", "puptoo", "rhsm-conduit", "rhsm-system-profile-bridge", "yuptoo"]
        )

    return payload


def build_host_payload(payload_builder=build_host_chunk):
    return payload_builder()


# for testing rhsm-conduit, comment out b64_identity and provide subscription_manager_id in host.
def build_mq_payload(payload_builder=build_host_chunk):
    message = {
        "operation": "add_host",
        "platform_metadata": {
            "request_id": random_uuid(),
            "archive_url": "http://s3.aws.com/redhat/insights/1234567",
            "b64_identity": apiKey.decode("ascii"),
        },
        "data": build_host_payload(payload_builder),
    }
    return json.dumps(message).encode("utf-8")


def build_http_payload(payload_builder=build_host_chunk):
    return build_host_payload(payload_builder)
