FROM registry.access.redhat.com/ubi8/python-38:1-54.1618436884

USER root

RUN dnf install -y postgresql

USER 1001

WORKDIR /opt/app-root/src
COPY . .

RUN pip install --upgrade pip && \
    pip install pipenv && \
    pipenv install --system --dev

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
