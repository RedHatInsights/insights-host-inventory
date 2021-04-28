FROM registry.redhat.io/rhel8/python-38

USER root
RUN dnf install -y postgresql-10.15-1.module+el8.3.0+8944+1ca16b1f.x86_64

USER 1001

WORKDIR /opt/app-root/src
COPY . .

RUN pip install --upgrade pip\
    && pip install pipenv\
    && pipenv install --system --dev

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
