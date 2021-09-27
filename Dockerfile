FROM registry.access.redhat.com/ubi8/python-38

USER root

# remove packages not used by host-inventory to avoid security vulnerabilityes
RUN dnf remove -y npm

# upgrade security patches and cleanup any clutter left.
RUN dnf upgrade -y --security
RUN dnf clean all -y

# The following RPM should be removed when a patched postgresql package becomes available in yum repos
# RUN dnf install -y postgresql
COPY postgresql-13.3-1.module+el8.4.0+11254+85259292.x86_64.rpm ./
RUN dnf install -y postgresql-13.3-1.module+el8.4.0+11254+85259292.x86_64.rpm

USER 1001

WORKDIR /opt/app-root/src
COPY . .

RUN pip install --upgrade pip && \
    pip install pipenv && \
    pipenv install --system --dev

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
