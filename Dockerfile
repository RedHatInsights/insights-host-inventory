FROM registry.access.redhat.com/ubi8/python-38

USER root

# remove packages not used by host-inventory to avoid security vulnerabilityes
RUN dnf remove -y npm

# upgrade security patches and cleanup any clutter left.
RUN dnf upgrade -y --security
RUN dnf clean all -y

RUN dnf module enable -y postgresql:13
RUN dnf install -y postgresql

USER 1001

WORKDIR /opt/app-root/src
COPY . .

RUN pip install --upgrade pip && \
    pip install pipenv && \
    pipenv install --system --dev

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
