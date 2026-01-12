# iqe-host-inventory-plugin

[![pipeline status](https://gitlab.cee.redhat.com/insights-qe/iqe-host-inventory-plugin/badges/master/pipeline.svg)](https://gitlab.cee.redhat.com/insights-qe/iqe-host-inventory-plugin/commits/master) [![coverage report](https://gitlab.cee.redhat.com/insights-qe/iqe-host-inventory-plugin/badges/master/coverage.svg)](https://gitlab.cee.redhat.com/insights-qe/iqe-host-inventory-plugin/commits/master)

## Overview

The contents of this repository provide a plugin for the iqe framework. This specific plugin's goal
is to provide both UI and REST service tests specific to Insight's inventory capabilities.

## Contents

* [Getting Started](#getting-started)
* [Running REST Service Tests](#running-rest-service-tests)
* [Running Frontend Tests (WIP)](#running-frontend-tests-wip)
* [Running tests in ephemeral environment](#running-tests-in-ephemeral-environment)
* [Running tests with local changes in ephemeral environment](#running-tests-with-local-changes-in-ephemeral-environment)
* [Markers](#markers)
* [Updating the REST service](#updating-rest-service)
* [Updating insights archives](#updating-insights-archives)
* [GitLab Configuration](#gitlab-configuration)
* [Accounts Configuration](#accounts-configuration)
* [Additional Accounts](#additional-accounts)
* [Preparing accounts for Test Day](#preparing-accounts-for-test-day)
* [Notifications testing](#notifications-testing)
* [Promoting deployments to Prod](#promoting-deployments-to-prod)
* [Jenkins Jobs](#jenkins-jobs)
* [Further Reading](#further-reading)

## Getting Started

At a high-level, there are basic tasks you need to complete to get your environment up and running:

Note: Minimum Python version needed for IQE is 3.12.

### Prerequisites

- Connect to the Red Hat VPN
- Make sure you have [Red Hat certificates](https://source.redhat.com/groups/public/identity-access-management/it_iam_pki_rhcs_and_digicert/faqs_new_corporate_root_certificate_authority)
installed in the system
(you can use `Current-IT-Root-CAs.pem`)
- Run the following command, you might want to also add it to your `~/.bashrc` file
```bash
$ export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
```

#### Install required Python version

Make sure you have the required version of Python installed. For Python versions management I
suggest to use [pyenv](https://github.com/pyenv/pyenv). You don't have to use pyenv, but make sure
you are using a correct Python version.

##### Pyenv

Here are general steps for pyenv installation on Fedora, but read the
[pyenv readme](https://github.com/pyenv/pyenv/blob/master/README.md) for more information:
```bash
$ sudo dnf install make gcc patch zlib-devel bzip2 bzip2-devel readline-devel sqlite sqlite-devel openssl-devel tk-devel libffi-devel xz-devel libuuid-devel gdbm-libs libnsl2
$ curl https://pyenv.run | bash
```

After this, follow the instructions from the pyenv install script and restart your shell session.

If you want to see the list of the available versions, you can use the `--list` option. Then,
install the Python version you want to use:
```bash
$ pyenv install --list | grep 3.12
$ pyenv install 3.12
```

Now, you can either set the installed Python version globally (`pyenv global 3.12`), or create a
new directory and set a local python version. This version will then also be used in all the
subdirectories:
```bash
$ mkdir iqe
$ cd iqe/
$ pyenv local 3.12
```

Now you can check that you are using the correct Python version:
```bash
$ python3 -V
Python 3.12
```

If you don't see correct version, try to restart your shell session.

#### Install required packages

```bash
$ sudo dnf install git krb5-devel gcc python3-devel podman
```

#### Vault access
When running IQE locally, you need to ensure you can access Vault.

First, you need to ensure you have a user file set up for your user in app-interface and
that you have the `insights-qe` and `insights-engineers` roles. See
[here](https://insights-qe.pages.redhat.com/iqe-core-docs/configuration.html#getting-access).

Then, [make sure you have the required environment variables set appropriately](https://insights-qe.pages.redhat.com/iqe-core-docs/configuration.html#using-vault-with-iqe-locally).
You might want to also add these to your `~/.bashrc` file, so you don't have to repeat it every
time:
```bash
$ export DYNACONF_IQE_VAULT_LOADER_ENABLED=true
$ export DYNACONF_IQE_VAULT_URL="https://vault.devshift.net/"
$ export DYNACONF_IQE_VAULT_VERIFY=true
$ export DYNACONF_IQE_VAULT_MOUNT_POINT="insights"
$ export DYNACONF_IQE_VAULT_OIDC_AUTH="1"
```

Please note: If you are not using Firefox or don't have Kerberos configured locally, you should set
the following:
```bash
$ export DYNACONF_IQE_VAULT_OIDC_HEADLESS="false"
```
Otherwise, the local test execution will hang during authentication.

If you want, you can read more about IQE
[here](https://insights-qe.pages.redhat.com/iqe-core-docs/tutorial/index.html).

### Installing the plugin to run the tests

```bash
# Setup the virtual environment
$ python3 -m venv venv

# Activate the virtual environment
$ source venv/bin/activate

# Setup pip to be able to download the iqe python proprietary packages from Nexus
$ pip install -U pip setuptools setuptools_scm wheel
$ pip config set global.index-url https://nexus.corp.redhat.com/repository/cqt-pypi/simple --site
$ pip config set global.index https://nexus.corp.redhat.com/repository/cqt-pypi/pypi --site

# Install IQE Framework from pip package
$ pip install iqe-core

# Install the plugin
$ iqe plugin install host-inventory
```

#### Possible setup issues
When running the previous setup steps, `pip install iqe-core` may fail, displaying a number of
`CERTIFICATE_VERIFY_FAILED` messages. If you encounter this, you probably don't have correct
[Red Hat certificates](https://source.redhat.com/groups/public/identity-access-management/it_iam_pki_rhcs_and_digicert/faqs_new_corporate_root_certificate_authority)
installed on your system. Running the following should help:

On LINUX:
```bash
$ sudo curl https://certs.corp.redhat.com/certs/Current-IT-Root-CAs.pem -o /etc/pki/ca-trust/source/anchors/Current-IT-Root-CAs.pem
$ sudo update-ca-trust
```

On Mac:
```bash
cat `python -m certifi` > ~/bundle.crt
curl https://certs.corp.redhat.com/certs/Current-IT-Root-CAs.pem >> ~/bundle.crt
export REQUESTS_CA_BUNDLE=~/bundle.crt
```

For the above you may get an error: `No module named certifi` if the `certifi` module isn't
installed. The solution is to simply:
```bash
# Run this outside the virtual environment initiated by 'virtualenv venv'
pip install certifi
```

### Installation Confirmation

Once you have the plugin installed, you can confirm its installation like this:

```bash
$ iqe plugin list
INSTALLED PLUGINS

Name                   Package                           Version
---------------------  --------------------------------  -----------------------------
host_inventory         iqe-host-inventory-plugin         24.5.13.0
```

Next, run a basic "operational check" for this plugin. This runs a single test to confirm the
plugin was installed successfully and is operational. Example command and output upon success are
included below.

```bash
$ iqe tests plugin host_inventory -k test_plugin_accessible
============================================================================================================= test session starts =============================================================================================================
platform linux -- Python 3.7.7, pytest-5.4.1, py-1.8.1, pluggy-0.13.1
Default Appliance hostname: qa.cloud.redhat.com
Default Appliance path: /
rootdir: /iqe-services/iqe-host-inventory-plugin, inifile: pytest.ini, testpaths: /iqe-services/iqe-host-inventory-plugin/iqe_host_inventory
plugins: iqe-host-inventory-plugin-6.0.7.dev0+gfe51b56.d20200520, iqe-red-hat-internal-envs-plugin-0.8.0, metadata-1.8.0, schemathesis-1.0.5, iqe-integration-tests-0.30.0, polarion-collect-0.23.1, cov-2.8.1, report-parameters-0.5.0, subtests-0.2.1, hypothesis-5.8.0, html-2.1.1, iqe-platform-ui-plugin-0.14.22
collected 458 items / 457 deselected / 1 selected

iqe_host_inventory/tests/test_plugin.py::test_plugin_accessible PASSED                                                                                                                                                                   [100%]

=============================================================================================== 1 passed, 457 deselected, 70 warnings in 0.34s ================================================================================================
```

### Install the plugin for development

If you want to develop the plugin and create or update the tests, you will need to clone this
repository and install the plugin to be editable. To do that, install the IQE the same way it is
described in the previous section (if you didn't already) and then do the following.

#### Prerequisites

If you want to push changes to the repository, you will have to
[set up SSH keys](https://docs.gitlab.com/ee/user/ssh.html) first.

#### Installation

```bash
# Clone the repository - use this if you have SSH keys
$ git clone git@gitlab.cee.redhat.com:insights-qe/iqe-host-inventory-plugin.git

# Clone the repository - use this if you don't have SSH keys
$ git clone https://gitlab.cee.redhat.com/insights-qe/iqe-host-inventory-plugin.git

# CD into the plugin directory
$ cd iqe-host-inventory-plugin

# Install the plugin
$ iqe plugin install --editable .
```

## Running REST Service Tests

Assuming you have the environment set up correctly, the basic command to run the rest service tests
looks like this:

```bash
# run all rest tests
$ ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory -m 'backend and not ephemeral'

# run only smoke tests
$ ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory -m 'backend and smoke and not ephemeral'
```

Be forewarned that there are a considerable number of tests, so you will receive quite a
significant amount of console output from running this command and if you run all the tests, it
will take about an hour.

### Pointing to other environment

To point your tests to other environment just change the value of **ENV_FOR_DYNACONF** variable as:
**stage_proxy**, **fedramp_stage_proxy** or **prod** e.g.:

```bash
export ENV_FOR_DYNACONF=prod
```

You can find the default configuration for each environment in the
[iqe-core config](https://gitlab.cee.redhat.com/insights-qe/iqe-core/-/blob/master/iqe/conf/settings.default.yaml?ref_type=heads)
and the [iqe-host-inventory-plugin config](https://gitlab.cee.redhat.com/insights-qe/iqe-host-inventory-plugin/-/blob/master/iqe_host_inventory/conf/host_inventory.default.yaml?ref_type=heads).

To learn more about IQE Tests configuration, please click
[here](https://insights-qe.pages.redhat.com/iqe-core-docs/configuration.html#)


## Running Frontend Tests (WIP)

IQE supplies a container to run Selenium which enables UI tests to work. The container contains the following:
* Selenium Server
* VNC server
* browsers (Firefox or Chrome)

First, pull the latest selenium image and start the selenium container:
```bash
$ podman pull quay.io/redhatqe/selenium-standalone
$ podman run -it --shm-size=2g -p 4444:4444 -p 5999:5999 quay.io/redhatqe/selenium-standalone
```

If you want to watch what the UI tests are doing, you can run a VNC viewer.
Install the TigerVNC, if you don't have it already:
```bash
$ sudo dnf install tigervnc
```

Now launch the VNC viewer and connect it to the VNC server:
```bash
$ vncviewer 127.0.0.1:5999
```

For more information about the selenium container follow the IQE documentation:
[Running a basic UI test](https://insights-qe.pages.redhat.com/iqe-core-docs/tutorial/part2.html#running-a-basic-ui-test).


Assuming you have the environment set up correctly and selenium container is started, you should now able to run UI tests. All frontend tests are marked with `ui` pytest marker.

```bash
# run all UI tests
$ ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory -m 'ui'

# run all UI RBAC tests
$ ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory -m 'ui and rbac_dependent'
```


## Running tests in ephemeral environment

First, you need to go through a quick
[on-boarding](https://consoledot.pages.redhat.com/docs/dev/creating-a-new-app/using-ee/getting-started-with-ees.html)
to the ephemeral environments.

Then follow these steps:

* Reserve a namespace with:
`NAMESPACE=$(bonfire namespace reserve -d <hours_to_reserve (at least 2)>)`
* Deploy HBI to that namespace:
    * backend:`bonfire deploy --source appsre --ref-env insights-stage host-inventory -n $NAMESPACE`
    * frontend: `bonfire deploy --source appsre --ref-env insights-stage host-inventory -n $NAMESPACE --frontends=true`
* Run the tests:
    * backend:`POD=$(bonfire deploy-iqe-cji host-inventory -m "backend and not resilience and not cert_auth and not rbac_dependent" -n $NAMESPACE)`
    * frontend: `POD=$(bonfire deploy-iqe-cji host-inventory --env ephemeral --selenium -m "ui and smoke" -n $NAMESPACE)`
* To see the live results: `oc logs -n $NAMESPACE $POD -f`
* Run graceful shutdown tests:
`POD=$(bonfire deploy-iqe-cji host-inventory -m "backend and resilience" -n $NAMESPACE)`
* To see the live results: `oc logs -n $NAMESPACE $POD -f`

You can run graceful shutdown tests together with other tests, but it is recommended to run them
separately, because they can be destructive, and they could affect results of the other tests.

The reason why we skip e2e cert auth tests (`-m "not cert_auth"`) is that when we use
`ENV_FOR_DYNACONF=clowder_smoke`, which is the default env in ephemeral, then we send direct
requests to HBI (and other services) with identity headers, so we can't use any real world
authentication method (basic, jwt, cert), because the requests don't go through a gateway (3scale)
which would verify the authentication. Instead, we have tests that simulate different
authentication methods in the identity header, see `tests/rest/rest_identity`.

We also skip RBAC tests (`-m "not rbac_dependent"`), because
[HBI bypasses RBAC by default in ephemeral environments](https://gitlab.cee.redhat.com/service/app-interface/-/blob/f8ca346a10a0c9a22ac13dcddda72b8d489c9d9a/data/services/insights/host-inventory/deploy-clowder.yml#L199).
To run the RBAC tests in ephemeral, we have to override the `BYPASS_RBAC` parameter during the
deployment. To do that, reserve a new namespace and then add `-p host-inventory/BYPASS_RBAC=false`
to your deployment command:
```bash
$ bonfire deploy host-inventory --source appsre --ref-env insights-stage -p host-inventory/BYPASS_RBAC=false -n $NAMESPACE
```

Now you can run the tests without skipping the RBAC tests. However, you have to make sure you skip
the service accounts tests (`-m "not service_account"`), because of the same reason why we skip
cert auth tests (see above). So, if you wanted to run all the tests now, the command would look
like this:
```bash
$ POD=$(bonfire deploy-iqe-cji host-inventory -m "backend and not resilience and not cert_auth and not service_account" -n $NAMESPACE)
```

## Running tests with local changes in ephemeral environment


### Backend tests


First, reserve a namespace and deploy `host_inventory` to your namespace, as in the previous
section:

1. Reserve a namespace with:
`NAMESPACE=$(bonfire namespace reserve -d <hours_to_reserve (at least 2)>)`
2. Deploy HBI to that namespace:
`bonfire deploy --source appsre --ref-env insights-stage host-inventory -n $NAMESPACE`

Once it's deployed, instead of running the tests immediately, you need to copy your local changes
to the pod first. To deploy the pod without running the tests, just add `--debug-pod` option at the
end of the `deploy-iqe-cji` command:

3. Deploy the pod:
```bash
POD=$(bonfire deploy-iqe-cji --debug-pod host-inventory -m "backend and not resilience and not cert_auth and not rbac_dependent" -n $NAMESPACE)
```

4. Install setuptools in the pod:
```bash
oc rsh -n $NAMESPACE $POD pip install -i https://pypi.python.org/simple setuptools_scm
```

5. Copy your local changes to the pod:

You have two options for copying files: `oc cp` (one-time copy) or `oc rsync` (continuous sync).

#### Option A: One-time copy with `oc cp`

Use this when you just want to copy files once and run tests:

```bash
# Make sure you're in the iqe-host-inventory-plugin directory
oc cp -n $NAMESPACE . $POD:iqe-host-inventory-plugin
```

#### Option B: Continuous sync with `oc rsync` (Recommended for active development)

Use this when you're actively developing and want file changes to automatically sync to the pod.

**Advantages:**
- Automatically syncs file changes as you save them
- No need to manually copy files after each change
- Faster iteration during development
- Only syncs changed files (more efficient than `oc cp`)

**Setup:**

a. In your current terminal, make sure you're in the `iqe-host-inventory-plugin` directory

b. Set up continuous sync using `watch` (updates every second):
```bash
watch -n 1 "oc rsync -n $NAMESPACE --exclude='.git' --exclude='*.pyc' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='venv' . $POD:iqe-host-inventory-plugin"
```

**What this does:**
- `watch -n 1` - Runs the rsync command every 1 second
- `--exclude` flags - Prevents syncing unnecessary files (git history, Python cache, virtual env)
- Automatically detects and syncs only changed files

**Tip:** Keep this terminal open while developing. You'll see output each time files are synced to the pod.

6. Initiate shell session in the pod:
```bash
oc rsh -n $NAMESPACE $POD
```

7. Change directory to the `iqe-host-inventory` plugin and install it:
```bash
cd iqe-host-inventory-plugin/
pip install -i https://pypi.python.org/simple -e .
```

8. Run the tests:

Now you can run the tests the same way you would do it locally. For example:
```
iqe tests plugin host_inventory -k "test_create_single_host"
```
**Tip**: Every time you start the tests in ephemeral, it will automatically create some hosts and
groups on the secondary account. This is because we need some data in the secondary account to be
able to catch data leaks between accounts. However, this setup takes some time and if you just want
to test out your new iqe-hbi-plugin changes, it's not needed. So you can use `--skip-data-setup`
option when you start the tests to skip the secondary account hosts and groups setup:
```
iqe tests plugin host_inventory --skip-data-setup -k "test_create_single_host"
```

### Frontend tests


1. Reserve a namespace with:
`NAMESPACE=$(bonfire namespace reserve -d <hours_to_reserve (at least 2)>)`
2. Deploy HBI and frontend components along with their dependencies (`--frontends=true`) to that namespace:
`bonfire deploy --source appsre --ref-env insights-stage host-inventory -n $NAMESPACE --frontends=true`
3. Deploy the pod:

To run frontend tests in ephemeral, the -`-env ephemeral` and `--selenium` options are required:
`POD=$(bonfire deploy-iqe-cji --debug-pod host-inventory --env ephemeral --selenium -m "ui and smoke" -n $NAMESPACE)`

Once pod is deployed, in pod's logs you can see one of the containers is selenium container.
Optional step: if you want to see what browser is doing you can connect VNC server (port as an example):
```
oc port-forward $POD 5999:5999 -n $NAMESPACE
```
Then open VNC: `vncviewer 127.0.0.1:5999`

4. To initiate a shell session in the pod and run frontend tests, follow steps 4-8 from backend tests above.



## Markers

We have all the markers. You might say we have the _best_ markers. As you review the code you
may come across a variety of markers on various tests. This section enumerates known markers and
their meaning.

If you are unfamiliar with pytest markers, you may wish to review the pytest project's
documentation on the subject.

* `backend` - All tests related to backend
* `ui` - All tests related to frontend
* `outage` - Tests intended to be used as an evaluation of whether the production environment is in
a "working" state.
* `core` - Tests for <prod/stage>-test-suite pipeline
* `smoke` - Smoke tests for HBI PR checks (generally, tests with critical importance and critical
requirements)
* `ephemeral` - Tests executable only in ephemeral environment
* `concurrency` - Tests that involve making multiple concurrent requests against a given endpoint
* `multi_account` - Tests that require two different application user accounts to execute
* `reaper_script` - Tests that need to run HBI reaper script
* `resilience` - Tests intended to verify the graceful shutdown of the HBI services
* `cert_auth` - Tests that require certificates for authorization
* `rbac_dependent` - Tests that require RBAC to be running
* `service_account` - Tests that require service accounts
* `extended` - Tests that might run for an extended time

Make sure you specify `backend` or `ui` markers when you [run required tests](#running-rest-service-tests).

## Updating Rest service

Due to [ESSNTL-619](https://issues.redhat.com/browse/ESSNTL-619) the spec in our repository is
currently not in sync with the upstream spec. While that is the fact, we need to manually copy over
changes to the schema.

1. edit `$ $EDITOR iqe_host_inventory/data/api.host_inventory.api.spec.json`
1. edit `$ $EDITOR iqe_host_inventory/data/api.host_inventory.api_v7.spec.json`
2. install iqe goatee plugin `$ iqe plugin install goatee`
3. install and setup correctly a `Java` runtime beforehand
4. run `$ iqe apigen generate-api host_inventory api`
5. run `$ iqe apigen generate-api host_inventory api_v7`

Its critical we keep our own spec in sync so later codegen runs won't destroy our work.


## Updating insights archives

One of the methods we use to create/update hosts in Inventory is uploading pre-collected insights
archives to Ingress. The archive is then processed by some ingress pipeline services, and it will
end up in puptoo which will send a Kafka message to Inventory. HBI will process this message, and
it will create or update a host.

In the real world these archives are generated by insights-client on a customer's machine. In our
testing we use old archives which were pre-collected by insights-client some time ago, and then we
modify these archives to give them the properties we need, for example different insights_id,
subscription_manager_id, or operating_system.

From time to time these old pre-collected archives stop working as expected, usually due to some
deprecation on puptoo or insights-core side. This means that the new versions of insights-client
collect the data in a different way and the old format of the archive is no longer supported. In
this case we need to generate a new insights archive which will be used for the testing.

### Collecting new insights archive

First, we need to provision a new RHEL (or CentOS) VM on which we will collect the new archive.
Instructions on how to provision a new VM, ssh into it and register the RHSM can be found
[here](https://docs.google.com/document/d/1j-_ekqxt3wjuKzuEeUP7iA-l54_b1z5ykb3H_-ygNHA/edit?tab=t.0#heading=h.b48lj6i0cpdx).

When you have the VM running and it is registered via subscription-manager, run
`insights-client --register --keep-archive`. Insights-client will tell you where it saved the
collected archive. Copy this archive to the `/tmp/` directory and download it to your local
computer. To do that, run
`scp -i ~/.ssh/insights-qa.pem cloud-user@<VM-IP>:/tmp/<archive-name> /destination/path` from your
computer.

### Making the OS adjustable

In our tests we sometimes need to create hosts with a specific OS. To do that we automatically
modify the `/etc/redhat-release` file in the archive before we upload it to Ingress. However, if
you do this on a newly collected archive, you will find that it doesn't work. To understand why,
let's look at how puptoo determines the OS.

Puptoo uses
[RedhatRelease combiner](https://github.com/RedHatInsights/insights-puptoo/blob/345c4a79ccaa228e1325ecc5a8e03e2c5615282b/src/puptoo/process/profile.py#L490)
from [insights-core](https://github.com/RedHatInsights/insights-core/blob/master/insights/combiners/redhat_release.py)
to determine the OS. This combiner looks at 2 places to get the OS information:
- results of the `uname -a` command:
[Uname parser](https://github.com/RedHatInsights/insights-core/blob/master/insights/parsers/uname.py)
- contents of the `/etc/redhat-release` file:
[RedhatRelease parser](https://github.com/RedHatInsights/insights-core/blob/master/insights/parsers/redhat_release.py)

The results of the `uname -a` command take precedence, so if we just change the contents of the
`/etc/redhat-release` file in our archive, it will not change the final OS version. This is why we
need to manually change the results of the `uname -a` command in our newly collected archive before
we start using it for testing (Only if we want to make the OS adjustable in this archive. If not,
then you can skip this step).

So, how does the Uname parser know which version of RHEL we are using? It looks at the Linux kernel
version information and determines the RHEL version from that. Here is a
[rhel_release_map](https://github.com/RedHatInsights/insights-core/blob/601b1814c6dfdac2f32f48be9457c463e5574fb4/insights/parsers/uname.py#L49)
used by insights-core to map the Linux kernel version to the RHEL release version.

Now, let's look at the `uname -a` results stored in your new archive. First, uncompress the archive
with `tar -xzf <path-to-archive>`. Now, look at the file at
`<uncompressed-archive-dir>/data/insights_commands/uname_-a`. You should see something like this:
```
Linux iqe-vm-cli-80196d0a-2704-4b38-bad0-8eacc6feda7d 5.14.0-427.13.1.el9_4.x86_64 #1 SMP PREEMPT_DYNAMIC Wed Apr 10 10:29:16 EDT 2024 x86_64 x86_64 x86_64 GNU/Linux`
```
The important part for us is the Linux kernel version info `5.14.0-427` right after the
`Linux <VM-name>` part. If we look at the
[rhel_release_map](https://github.com/RedHatInsights/insights-core/blob/601b1814c6dfdac2f32f48be9457c463e5574fb4/insights/parsers/uname.py#L128)
 we can see that `5.14.0-427` corresponds to RHEL 9.4. This means that it doesn't matter what we
put into the `/etc/redhat-release` file, as long as this kernel version is going to be there, the
OS will always be RHEL 9.4.

So, how to fix it? Easy. The only thing we have to do is to put a different kernel version into
this file, one that isn't mapped to any RHEL version. For example, we can do just a very small
modification and change it to `5.14.0-426`. Now, the Uname parser will fail to determine the OS
version and the contents of `/etc/redhat-release` will be used instead. So, modify the kernel
version in the `<uncompressed-archive-dir>/data/insights_commands/uname_-a` file in your archive.
Then compress the modified data and create a new archive:
`tar -czf <archive-name>.tar.gz <uncompressed-archive-dir>/`

### Making the new archive available for testing

All the archives we currently use for testing are located in the
[iqe-ingress-plugin](https://gitlab.cee.redhat.com/insights-qe/iqe-ingress-plugin/-/tree/master/iqe_ingress/resources/archives?ref_type=heads).
To make your new archive available, simply copy it to the `iqe_ingress/resources/archives`
directory in the iqe-ingress-plugin, create an MR, and make sure it gets merged and released. Once
that's done, you can modify the name of the default insights archive we use in testing
[here](https://gitlab.cee.redhat.com/insights-qe/iqe-host-inventory-plugin/-/blob/4e38cc8d394723756fdd658552ebe8a2daf0fd6a/iqe_host_inventory/utils/upload_utils.py#L49).
Optionally, you can also change the default OS version
[here](https://gitlab.cee.redhat.com/insights-qe/iqe-host-inventory-plugin/-/blob/4e38cc8d394723756fdd658552ebe8a2daf0fd6a/iqe_host_inventory/utils/datagen_utils.py#L68).


## Deprecating Code

Occasionally, test code like fixtures, utilities, and/or other supporting functionality will be
updated or removed.  As there may be dependencies on these functions within this plugin or in
other plugins, this code should first be deprecated to allow time for dependent code to be updated.

The IQE framework provides deprecation support.  Please refer to the IQE [deprecation instructions](https://insights-qe.pages.redhat.com/iqe-core-docs/deprecations.html) for
guidance on this process.


## GitLab Configuration

If you review the GitLab CI file in this repo (`.gitlab-ci.yml`), you'll notice two jobs that can
be manually executed as part of any pipeline.

1. `unit_test` - This job will run the unit tests from the master branch of the service. Useful for
getting coverage information.
2. `functional_test` - This will run a subset of all the functional tests within an ephemeral
environment.

Both of these jobs should be considered experimental. The `unit_test` job tends to execute
reliably. The `functional_test` job succeeds intermittently. Investment to stabilize these jobs has
been minimal, primarily because there has been heavy investment in Jenkins as the tool of choice
for executing test runs.


## Accounts Configuration

We have an account called `insights-inventory-qe` in both Stage and Prod. This is our main account
where we run the majority of our tests. This account has 4 users, the main org admin user
(`insights-inventory-qe`), a non org admin user which we use for RBAC testing
(`insights-inventory-qe-2`), and 2 non org admin users which we use for notifications testing
(`insights-inventory-qe-notifications` and `insights-inventory-qe-notifications-digest`).
In some of the tests we also use the shared `insights-qa` account to test that one account doesn't
have access to another account's data.

Currently, all of these accounts are correctly set, so if you want to run the tests, you don't have
to do anything. However, approximately once a year there is a Stage env refresh. When the refresh
happens, all the data and accounts from Stage are deleted. Accounts which exist in Prod will be
cloned to Stage during the refresh, but without any data (including RBAC and notifications
settings). All the accounts we use for testing are available in Prod, so we don't have to create
any new accounts in Stage after the refresh, but we have to set them up after the refresh.

### Setting up accounts after Stage refresh

After Stage refresh, all of our Prod accounts will be copied to Stage. Our Prod accounts have
these email addresses:
- `insights-inventory-qe`: `insights-inventory-qe+insights-inventory-qe@redhat.com`
- `insights-inventory-qe-2`: `insights-inventory-qe+insights-inventory-qe-2@redhat.com`
- `insights-inventory-qe-notifications`: `insights-qe+insights-inventory-qe-notifications@redhat.com`
- `insights-inventory-qe-notifications-digest`: `insights-qe+insights-inventory-qe-notifications-digest@redhat.com`

These will be copied to the Stage accounts with an additional "+stage" at the end:
- `insights-inventory-qe`: `insights-inventory-qe+insights-inventory-qe+stage@redhat.com`
- `insights-inventory-qe-2`: `insights-inventory-qe+insights-inventory-qe-2+stage@redhat.com`
- `insights-inventory-qe-notifications`: `insights-qe+insights-inventory-qe-notifications+stage@redhat.com`
- `insights-inventory-qe-notifications-digest`: `insights-qe+insights-inventory-qe-notifications-digest+stage@redhat.com`

We don't need to change the email addresses, they can stay as they are. First thing we have to do
is to change the passwords for our accounts. The passwords should be set to the usual password we
use in Stage accounts. To change the password, you will have to click on the
*Forgot your password?* link when logging in to the console.stage.redhat.com, which will trigger an
email to the current email address.
`insights-inventory-qe@redhat.com` is a mailing list (Google Group) which you can subscribe to from
your Red Hat account through [Google Groups](https://groups.google.com).
`insights-qe@redhat.com` is an email account. You can log in via Gmail. After typing in
`insights-qe@redhat.com` as a username in Gmail, you will be redirected to RH SSO. There, use
`insights-qe` as a username, and use the password from
[Vault](https://vault.devshift.net/ui/vault/secrets/insights/show/secrets/qe/global/insights-qe-sa)
(*insights/secrets/qe/global/insights-qe-sa*)) as `PIN+token`.

### Set RBAC permissions for the users

We need to make sure that our users have correct RBAC permissions needed for testing. Our org admin
user needs to have full access, while `insights-inventory-qe-2` needs to have zero permissions by
default (it will get specific permissions automatically during the test run). Both notifications
users need to have read access to Inventory hosts and admin access to Notifications. To do this,
log in as `insights-inventory-qe` on Stage, then click on the gear icon next to your profile icon
and select *User access*. Then click on
*[Groups](https://console.stage.redhat.com/iam/user-access/groups)*. Click on the *Default access*
group, select all roles, click on three dots next to the *Add role* button, click *Remove* and
confirm.

Then go back to the [Groups](https://console.stage.redhat.com/settings/rbac/groups) page and create
these new RBAC groups:
- **Group name**: `Admin`
- Select all roles (on all pages)
- Select `insights-inventory-qe` member
- Don't select any service account


- **Group name**: `Notifications - Instant`
- Select `Inventory Hosts Viewer` and `Notifications administrator` roles
- Select `insights-inventory-qe-notifications` member
- Don't select any service account


- **Group name**: `Notifications - Digest`
- Select `Inventory Hosts Viewer` and `Notifications administrator` roles
- Select `insights-inventory-qe-notifications-digest` member
- Don't select any service account

The reason why we need 2 separate RBAC groups for the notifications users, even though they have
the same permissions, is described in the [Configure notifications](#configure-notifications)
section.

### Create service accounts

We also need to test Inventory with Service Accounts. These will probably get deleted after the
Stage refresh as well, so they need to be recreated. To do that, log in as `insights-inventory-qe`
on Stage, click on the gear icon next to your profile icon and select
*[Service Accounts](https://console.stage.redhat.com/iam/service-accounts)*. From there, create 2
service accounts:

**First:**
- **Service Account Name**: `hbi-service-acc-all-perms`
- **Short description**: `Service Account with all RBAC permissions, used for HBI testing`

**Second:**
- **Service Account Name**: `hbi-service-acc-none-perms`
- **Short description**: `Service Account with none RBAC permissions, used for HBI testing`

When you click on *Create*, you will be presented with the credentials (*Client ID* and *Client
secret*). Copy the credentials, you will need them later (when you'll add them to the Vault)

#### Set RBAC permissions for the service accounts

Now, we have to set RBAC permissions for our new service accounts. This is very similar to the
permissions for our users. This time, we will have to create 2 RBAC groups:

**First:**
- **Group name**: `ServiceAccountAdmin`
- Select all roles (on all pages)
- Don't select any member
- Select `hbi-service-acc-all-perms` service account

**Second:**
- **Group name**: `ServiceAccountRegular` (it's important to keep the name)
- Don't select any roles
- Don't select any member
- Select `hbi-service-acc-none-perms` service account

### Configure notifications

First, we have to configure notification preferences for our notifications users. Log in as
`insights-inventory-qe-notifications` and go to Services -> Integrations and Notifications ->
Notifications ->
[Notification Preferences](https://console.stage.redhat.com/settings/notifications/user-preferences).
Search for *Inventory* service, select it, enable all **Instant notifications**, and disable all
**Daily digest** notifications. Then log out and log in as
`insights-inventory-qe-notifications-digest` user. Go to **Notification Preferences** again and
this time enable all **Daily digest** notifications for Inventory. Also, make sure that all
**Instant notifications** are disabled, to reduce the email noise.

_Note: At the time of writing this documentation, there is a bug in UI which prevents some users
from setting their notification preferences through UI.
[Here](https://redhat-internal.slack.com/archives/C023VGW21NU/p1724154426937589) is a slack thread
for reference. If the issue is still not fixed, you can set the preferences via API by running
these curl commands:_

```bash
curl -k -H 'accept: application/json, text/plain, */*' -H 'Content-Type: application/json' -vvv -X POST --user insights-inventory-qe-notifications:<password> -d '{"bundles": {"rhel": {"applications": {"inventory":{"eventTypes":{"new-system-registered":{"emailSubscriptionTypes":{"INSTANT":true,"DAILY":false}},"system-became-stale":{"emailSubscriptionTypes":{"INSTANT":true,"DAILY":false}},"system-deleted":{"emailSubscriptionTypes":{"INSTANT":true,"DAILY":false}},"validation-error":{"emailSubscriptionTypes":{"INSTANT":true,"DAILY":false}}}}}}}}' https://console.stage.redhat.com/api/notifications/v1/user-config/notification-event-type-preference
curl -k -H 'accept: application/json, text/plain, */*' -H 'Content-Type: application/json' -vvv -X POST --user insights-inventory-qe-notifications-digest:<password> -d '{"bundles": {"rhel": {"applications": {"inventory":{"eventTypes":{"new-system-registered":{"emailSubscriptionTypes":{"INSTANT":false,"DAILY":true}},"system-became-stale":{"emailSubscriptionTypes":{"INSTANT":false,"DAILY":true}},"system-deleted":{"emailSubscriptionTypes":{"INSTANT":false,"DAILY":true}},"validation-error":{"emailSubscriptionTypes":{"INSTANT":false,"DAILY":true}}}}}}}}' https://console.stage.redhat.com/api/notifications/v1/user-config/notification-event-type-preference
```

Now, log in as the org admin user (`insights-inventory-qe`) and create a Notifications Behavior
Group (BG) for the daily digests. To do that, go to Notifications -> Configure Events ->
[Behavior Groups](https://console.stage.redhat.com/settings/notifications/configure-events?bundle=rhel&tab=behaviorGroups)
 and click on *Create new group*:

- **Group name**: Inventory Notification Digest
- **Actions**: Send an email
- **Recipient**: Notifications - Digest
- Select all Inventory event types (you can filter them by Service)

Here we can see the reason why we had to create 2 different RBAC groups in the
[Set RBAC permissions for the users](#set-rbac-permissions-for-the-users) section. When we are
creating a BG, we can't select individual users, but we have to select them through RBAC groups.
Now, the notifications setup is complete. If you want to know more about how the notifications
testing works, see [Notifications testing](#notifications-testing) section.

### Update secrets in vault

Go to Stage users in [Vault](https://vault.devshift.net/ui/vault/secrets/insights/list/secrets/qe/stage/users/) and update `insights_inventory_qe` and `insights_inventory_qe_2`
by clicking on *Create new version* button. `username` and `password` should stay the same.
`account_number` and `org_id` should hopefully also stay the same, but you can check them when you
click on your profile icon in *console.stage.redhat.com*.

In the `insights_inventory_qe` vault secret, you should also update the service accounts
credentials. Here, use the secrets you copied when you created the service accounts.

#### Getting RHSM certificates

To get `cert` and `key`, you will have to
[provision new VMs](https://docs.google.com/document/d/1j-_ekqxt3wjuKzuEeUP7iA-l54_b1z5ykb3H_-ygNHA/edit#heading=h.b48lj6i0cpdx).
Provision 2 VMs (one for each user) and ssh into them via
`ssh -i ~/.ssh/insights-qa.pem cloud-user@<IP-address>` (you will need `insights-qa.pem` for that,
you can find it in the
[Vault](https://vault.devshift.net/ui/vault/secrets/insights/show/secrets/qe/global/insights-qa-pem)
(*insights/secrets/qe/global/insights-qa-pem*)).

Then follow these steps inside the VM:
- `sudo su -`
- `subscription-manager unregister`
- `subscription-manager clean`
- `subscription-manager register --serverurl=subscription.rhsm.stage.redhat.com --username=insights-inventory-qe(-2) --password=<account-password>`

Then you can find the `cert` and the `key` in `/etc/pki/consumer/<cert/key>.pem`. Simply cat the
files and add its contents to the Vault.

You can delete the VMs afterward, but don't do `subscription-manager unregister`. That would
disable the certificates.

### Generate insights archives from edge systems

We need special insights archives for testing edge hosts. Edge archives always have to be generated
on a system built from an existing image in the
[Image Builder](https://console.stage.redhat.com/insights/image-builder/manage-edge-images),
because the edge hosts always have to match an existing image. If you upload an edge archive from
a non-existing image (or an image from a different account), the new host will be created in our
Insights Inventory without any problems (in backend), but it will not appear in the Edge Inventory.
So, to test the Edge integration properly, we need to make sure we always have valid archives.
After the Stage refresh, the images should stay in the account. You can check if
`IQE-TEST-IMAGE-RHEL...` exists in the Image Builder. If it does, you don't have to do anything.
If the image is missing, you need to create a new one and generate a new archive.
[Here](https://docs.google.com/document/d/1zNPXD7fayRRLVrQ7e7DknNM08nuQku0ik5-lY-NXG3A/edit?tab=t.0)
are instructions for doing that. Once you have the image, create an MR against
[iqe-ingress-plugin](https://gitlab.cee.redhat.com/insights-qe/iqe-ingress-plugin/-/blob/master/iqe_ingress/resources/archives/edge_stage_inventory.tar.gz?ref_type=heads)
and upload the new archive as `edge_stage_inventory.tar.gz`.


## Additional accounts

Generally, we don't need any more accounts. However, sometimes you might want to create a new one
in Stage. For example, to test some special new feature, which will be enabled only on a specific
set of accounts. For that, you can use Ethel.

### Create org admin account

Create the main account via [Ethel](http://account-manager-stage.app.eng.rdu2.redhat.com/#create):
- **Username**: something that will represent the purpose of the account
- **Password**: we can use the same password as for the default test account
- **First Name** and **Last Name**: leave empty
- **Email**: use the Stage notifications email group, so that everyone has access to it in case you
are not available. Format: `insights-qe-stage-notifications+<new-username>@redhat.com`
- **Subscription SKUs**: use the same SKUs as the default account has - you can check those in the
[View Account](http://account-manager-stage.app.eng.rdu2.redhat.com/#view) tab
- **Quantity** and **Custom Validity Period**: leave empty
- **SCA**: `Enabled`
- **Accept Terms and Conditions**: `Yes`
- **Environment**: `Stage`

After the account is created successfully, you can log in to the account on the
[Consoledot Page](https://console.stage.redhat.com). You should be able to log in
immediately, but when you click on your profile icon in the top right corner,
the *Account number* will be probably missing there and also you will not be able
to see the gear icon next to the question mark icon. You will have to wait a few
minutes until these two things appear.

### Create the secondary user

Next, you will have to go to the
[User Management page](https://www.stage.redhat.com/wapps/ugc/protected/usermgt/userList.html) (you
can get there by clicking on the profile icon -> My profile -> Profile icon on the top right ->
User Management).
Make sure that you are logged in to your new account and click on
[Add New User](https://www.stage.redhat.com/wapps/ugc/protected/usermgt/createNewUser.html).
- **Greetings**: up to you
- **First name**: `first_name2`
- **Last name**: `last_name2`
- **Position/Job Title**: `QE`
- **Department**: leave empty
- **Email**: use the Stage notifications email group, so that everyone has access to it in case you
are not available. It will be needed for setting up the password. Format:
`insights-qe-stage-notifications+<new-username>@redhat.com`
- **Country or Region**: `United States`
- **Address line 1**: `100 E. Davie St.`
- **Address line 2** and **Address line 3**: leave empty
- **Postal code**: `27601`
- **City**: `Raleigh`
- **County**: `Wake`
- **State**: `North Carolina`
- **Phone number**: `1234567890`
- **Fax number**: leave empty
- **Red Hat login**: something that will represent the purpose of the user
- **Customer Portal Access Permissions**: check everything +
`View/Edit User's Only` in `Manage Your Subscriptions`
- **Account Roles**: leave `Organization Administrator` unchecked

After the user is created, change its password to the same password as default user has. You can do
that by trying to log in as the new user and clicking on *Forgot your password?*

## Preparing accounts for Test Day

In Stage, we have an account called `insights-test-day`, which is used during the Test Days.
This account has 31 users:
* The main org_admin user: `insights-test-day`
* 30 non org_admin users: `insights-test-day-01` - `insights-test-day-30`

Each user has their own RBAC group. They are called `Test Day User 01` - `Test Day User 30`.
Before the Test Day starts, we should setup all of these groups to contain only
`Inventory Hosts Administrator` and `Inventory Groups Administrator` roles.
In addition, we should remove all Inventory roles from the `Default access` or
`Custom default access` group. Also, we should delete all other RBAC groups.

In addition to preparing RBAC, we should also prepare hosts for each of the users.
You can use
[scripts/test-day-create-hosts.sh](https://gitlab.cee.redhat.com/insights-qe/iqe-host-inventory-plugin/-/blob/master/scripts/test-day-create-hosts.sh)
script for that. Always run the script in advance, because it can take up to 3 hours to complete.
Before running the script you need install
[iqe-advisor-plugin](https://gitlab.cee.redhat.com/insights-qe/iqe-advisor-plugin)
(`iqe plugin install advisor`).

For Test Days related to Edge hosts, we also have a secondary account called
`insights-edge-parity-special`. This is a special account configured to replicate the behavior of a
special customer account, which should use Edge Groups instead of Inventory Groups. This account
has 3 users:
* `insights-edge-parity-special`: This is an org-admin user
* `insights-edge-parity-special-01`: This is a non org-admin user, which should be configured to
have default non org-admin RBAC permissions (it has only `Inventory Hosts Administrator` role)
* `insights-edge-parity-special-02`: This is a non org-admin user which should have no Inventory
permissions at all.

To achieve this, you should remove all Inventory permissions from the `Default access` or
`Custom default access` RBAC group and ensure that there is only one additional RBAC group for
`insights-edge-parity-special-01` which contains only `Inventory Hosts Administrator` role.

If the Test Day is not related to Edge, feel free to comment out all hosts creations for
`$SPECIAL_ACCOUNT` in the hosts-creation script.

An example Test Day document:
[Edge Parity Test Day](https://docs.google.com/document/d/1pMEJJDlLSzGpbe_B6P8mGWkEyRSOZUglj1VrqzErjEg/edit)

## Notifications testing

This section explains how notifications and the testing of notifications works in more detail.

We have two kinds of notification tests. Ones that run in ephemeral environments and they check for
kafka messages produced by HBI to the `platform.notifications.ingress` topic, and then some E2E
tests which check the actual email notification (they run in Stage and Prod). The majority of the
testing is done through kafka, because these tests are very fast and flexible, and we can test a
lot of different combinations and scenarios this way.

_Note: If you want to run the E2E notifications tests, you have to
[configure accounts](#accounts-configuration) and
[configure notifications](#configure-notifications) first._

### How notifications work

If you want to receive notifications, you have to do 2 things:
- Set your notification preferences
- Your org admin has to create Behavior Groups (BG) where they map users to specific events (they
basically give you permissions for receiving the notifications for that specific event)

If the BG configures email notifications, and you enable them in your preferences, you will receive
the email to the email address that's linked with your Red Hat account.

### How E2E notification testing works

For E2E tests we are using tools from
[iqe-notifications-plugin](https://gitlab.cee.redhat.com/insights-qe/iqe-notifications-plugin).
At the time of writing this documentation, the notifications plugin uses a
[hard-coded account](https://gitlab.cee.redhat.com/insights-qe/iqe-notifications-plugin/-/blob/a2e1f73576672993114eb28ddb0ff2cd78d58cbb/iqe_notifications/utils/email_utils.py#L45)
for getting emails (`insights-qe`). There is an MR open to change that and let users define their
email credentials in their IQE config:
[iqe-notifications-plugin#574](https://gitlab.cee.redhat.com/insights-qe/iqe-notifications-plugin/-/merge_requests/574)

However, even if this change is merged, it would still be quite difficult (if not impossible) to
use our regular Stage/Prod users for getting the emails, because they use mailing lists as their
email addresses, so I don't think we can "log in" to them and fetch the emails. So, we will keep
using the `insights-qe` account for email fetching for now.

If we want to do that, we don't have to use the `insights-qe` account to execute our notifications
tests though. The workaround for using our own account for test execution and being able to fetch
the emails through the `insights-qe` account is that we create new users in our org, and we use
`insights-qe@redhat.com` as their email address. Then, whenever we execute the tests on our main
testing account, the tests create a BG which configures the notifications for all users in our org,
which means the emails will be sent to `insights-qe@redhat.com` too.

## Promoting deployments to Prod

The latest version of HBI (`master` branch in
[HBI backend](https://github.com/RedHatInsights/insights-host-inventory) and
[HBI frontend](https://github.com/RedHatInsights/insights-inventory-frontend)) is automatically
deployed to Stage.

Before we make any changes in Production, like change a config value, change a feature flag value,
or deploy new code, we always have to properly test these changes in Stage and Ephemeral
environments first. Here is what we need to do:

1. Make sure Stage has the same configuration we want to release to Production (all
[app-interface deployment config values](https://gitlab.cee.redhat.com/service/app-interface/-/blob/33eebcc3950ba1f06fa98985271adc73ef4e0ccd/data/services/insights/host-inventory/deploy-clowder.yml#L155),
[feature flags](https://insights-stage.unleash.devshift.net/projects), code image tags, etc.)
2. [Run tests in ephemeral environment](#running-tests-in-ephemeral-environment)
3. Run [HBI backend Stage pipeline](https://jenkins-csb-insights-qe-main.dno.corp.redhat.com/job/inventory/job/backend/job/-stage-basic/)
(for backend release) or [HBI frontend Stage pipelines](https://jenkins-csb-insights-qe-main.dno.corp.redhat.com/job/inventory/job/frontend/)
(for frontend release)

When everything passes, we can update Prod deploy config. For code releases, we need to update
these refs to match the tested version from Stage for backend:
- [HBI Backend](https://gitlab.cee.redhat.com/service/app-interface/-/blob/30fb5afe7babc91fe971e16a192d17eabd75ce8d/data/services/insights/host-inventory/deploy-clowder.yml#L191)
- [cyndi-operator](https://gitlab.cee.redhat.com/service/app-interface/-/blob/30fb5afe7babc91fe971e16a192d17eabd75ce8d/data/services/insights/xjoin/deploy-cyndi.yml#L76)
- [xjoin-kafka-connect](https://gitlab.cee.redhat.com/service/app-interface/-/blob/30fb5afe7babc91fe971e16a192d17eabd75ce8d/data/services/insights/xjoin/deploy.yml#L82)

And this ref for frontend:
- [HBI Frontend](https://gitlab.cee.redhat.com/service/app-interface/-/blob/30fb5afe7babc91fe971e16a192d17eabd75ce8d/data/services/insights/host-inventory/deploy-clowder.yml#L72)

The ref represents a commit hash of the latest commit we want to deploy to Production, so you can
look for the commit hash of the latest commit in master branches. Also, update all desired config
values in the same MR, if needed.

### Using app-interface-bot

If xjoin-kafka-connect doesn't have new commits that need to be deployed (it's a very stable repo,
so deploying new version of it to Prod is very rare), and we don't need to make any app-interface
config changes, it is preferred to use
[app-interface-bot](https://gitlab.cee.redhat.com/osbuild/app-interface-bot) to create the
release MR. This bot automatically scans the repositories and creates a release MR with the latest
commits. It also adds all released PRs and linked Jira cards to the description of the MR.

To run the app-interface-bot go to
[pipelines](https://gitlab.cee.redhat.com/osbuild/app-interface-bot/-/pipelines) and click
"New pipeline" in the top right corner of the page. Now select "host-inventory" for `HMS_SERVICE`,
and enter "master" (to release the latest commit) for the `HOST_INVENTORY_BACKEND` and
`CYNDI_OPERATOR` variables (for a backend release), or for the `HOST_INVENTORY_FRONTEND` variable
(for a frontend release). If the CI is failing in GitHub on the latest commit for an irrelevant
reason, and you are sure that it is OK, also choose "--force" on the `FORCE` variable. Now you can
click "New pipeline" and the bot will create the release MR for you in a few seconds. When it's
done, it will send a Slack message to `#insights-experiences-release` channel with the link to the
MR ([example](https://redhat-internal.slack.com/archives/C061D8JQ8BE/p1756802843458909)).

The bot is configured to automatically create these release MRs for backend on Mondays. Every time
it does so, carefully check if the release needs any config changes. For example, if the release
includes a DB migration, then there is a high chance that we want to reduce the number of MQ
replicas during this migration. In that case, feel free to close the MR either manually, or by
creating a new [pipeline](https://gitlab.cee.redhat.com/osbuild/app-interface-bot/-/pipelines) and
entering the MR ID for the `CLOSE_MR` variable. Then you can create a new release MR manually with
everything that's needed, and you can copy the description from the bot's release MR.

[Example release MR](https://gitlab.cee.redhat.com/service/app-interface/-/merge_requests/155681)

### Verifying the release MR and monitoring the deployment

Once the MR is created, carefully check all PRs that are going to be released and if everything is
OK and well tested (all Jira cards that are being released are in "Release pending" state, there is
no "On QA" Jira), then ask someone else from the Inventory team to also check the release MR and
approve it by adding a `/lgtm` comment.

Once the MR is merged and the new versions have settled in Prod, we can update feature flag values
in Prod, if needed.

After any change to Production, we always have to trigger one of our
[Prod pipelines](https://jenkins-csb-insights-qe-main.dno.corp.redhat.com/job/inventory/job/backend/)
to make sure everything is working fine. Also, the engineer who approved the MR is then responsible
for monitoring the deployment.

## Jenkins Jobs

1. [Stage and Prod HBI backend testing pipelines](https://jenkins-csb-insights-qe-main.dno.corp.redhat.com/job/inventory/job/backend/)
2. [Stage and Prod HBI frontend testing pipelines](https://jenkins-csb-insights-qe-main.dno.corp.redhat.com/job/inventory/job/frontend/)
3. [HBI backend outage check](https://jenkins-csb-insights-qe-main.dno.corp.redhat.com/job/inventory/job/backend/job/outage-check/)
4. [HBI frontend outage check](https://jenkins-csb-insights-qe-main.dno.corp.redhat.com/job/inventory/job/frontend/job/ui_outage-prod/)
5. [HBI RapiDAST pipeline](https://jenkins-csb-insights-qe-main.dno.corp.redhat.com/job/rapidast/job/Host-Inventory-rapidast-job/)
6. [IQE Stage Test Suite](https://jenkins-csb-insights-qe-main.dno.corp.redhat.com/job/common-pipelines/job/stage-test-suite/)
7. [IQE Prod Test Suite](https://jenkins-csb-insights-qe-main.dno.corp.redhat.com/job/common-pipelines/job/prod-test-suite/)
8. [host-inventory build-master](https://ci.ext.devshift.net/job/RedHatInsights-insights-host-inventory-gh-build-master/)
9. [host-inventory pr-checker](https://ci.ext.devshift.net/job/RedHatInsights-insights-host-inventory-pr-check/)
10. [host-inventory pr-checker full test run](https://ci.ext.devshift.net/job/RedHatInsights-insights-host-inventory-pr-check-all-tests/)
11. [host-inventory pr-checker rbac integration tests](https://ci.ext.devshift.net/job/RedHatInsights-insights-host-inventory-pr-check-rbac-tests/)

## Further Reading

* [OpenAPI Client Documentation](iqe_host_inventory_api_README.md) (generated automatically)
