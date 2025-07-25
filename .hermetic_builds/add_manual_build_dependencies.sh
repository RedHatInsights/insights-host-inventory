#!/bin/bash

echo "pipenv==2025.0.3" >> requirements-build.in
echo "wheel==0.45.1" >> requirements-build.in
echo "flit_core<4,>=3.8" >> requirements-build.in
echo "virtualenv>=20.24.2" >> requirements-build.in
echo "hatch-vcs==0.4.0" >> requirements-build.in
echo "hatchling==1.27.0" >> requirements-build.in
echo "calver==2025.4.17" >> requirements-build.in
echo "tomli==2.0.2" >> requirements-build.in
echo "setuptools-scm==8.2.1" >> requirements-build.in
echo "filelock<4,>=3.12.2" >> requirements-build.in
echo "dumb-init==1.2.5.post1" >> requirements-build.in
echo "pdm-backend==2.4.3" >> requirements-build.in
echo "coherent-licensed==0.3.0" >> requirements-build.in
echo "hatch-fancy-pypi-readme>=23.2.0" >> requirements-build.in
echo "poetry-core==2.1.3" >> requirements-build.in
echo "mypy==1.17.0" >> requirements-build.in
echo "mypy-extensions==1.1.0" >> requirements-build.in
echo "types-psutil==7.0.0.20250601" >> requirements-build.in
echo "types-setuptools==80.9.0.20250529" >> requirements-build.in
echo "typing-extensions==4.14.0" >> requirements-build.in
echo "flit-scm==1.7.0" >> requirements-build.in
echo "cython==3.1.2" >> requirements-build.in
echo "maturin==1.8.6" >> requirements-build.in
echo "setuptools-rust>=1.11.0" >> requirements-build.in
echo "cffi==1.17.1" >> requirements-build.in
echo "cfgv==3.4.0" >> requirements-build.in
echo "coverage==7.9.2" >> requirements-build.in
echo "cryptography==45.0.5" >> requirements-build.in
echo "identify==2.6.12" >> requirements-build.in
echo "iniconfig==2.1.0" >> requirements-build.in
echo "nodeenv==1.9.1" >> requirements-build.in
echo "pgxnclient==1.3.2" >> requirements-build.in
echo "pytest-runner==6.0.1" >> requirements-build.in
echo "pre-commit==4.2.0" >> requirements-build.in
echo "pygments==2.19.2" >> requirements-build.in
echo "alembic==1.16.3" >> requirements-build.in
echo "pytest==8.4.1" >> requirements-build.in
echo "pytest-cov==6.2.1" >> requirements-build.in
echo "pytest-mock==3.14.1" >> requirements-build.in
echo "pytest-subtests==0.14.2" >> requirements-build.in
echo "sqlalchemy-utils==0.41.2" >> requirements-build.in
echo "types-cffi==1.17.0.20250523" >> requirements-build.in
echo "types-pyopenssl==24.1.0.20240722" >> requirements-build.in
echo "types-python-dateutil==2.9.0.20250708" >> requirements-build.in
echo "types-pytz==2025.2.0.20250516" >> requirements-build.in
echo "types-pyyaml==6.0.12.20250516" >> requirements-build.in
echo "types-redis==4.6.0.20241004" >> requirements-build.in
echo "types-requests==2.32.4.20250611" >> requirements-build.in
echo "types-ujson==5.10.0.20250326" >> requirements-build.in

echo "setuptools-scm==7.1.0" >> requirements-extras.in
echo "tomli==2.0.2" >> requirements-extras.in
echo "typing-extensions==4.14.0" >> requirements-extras.in
echo "certifi==2025.7.14" >> requirements-extras.in
echo "mypy<=1.15.0,>=1.4.1" >> requirements-extras.in
