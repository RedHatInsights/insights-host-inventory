FROM registry.centos.org/centos/python-36-centos7

USER root
RUN yum update -y
RUN yum -y install centos-release-scl-rh
RUN yum -y install rh-postgresql10-postgresql
RUN sed -i 's/source scl_\(.*\)$/source scl_\1 rh-postgresql10/' /opt/app-root/etc/scl_enable
USER 1001

WORKDIR /opt/app-root/src
COPY . .

RUN scl enable rh-python36 "pip install --upgrade pip"
RUN pip install pipenv
RUN pipenv install --system --dev

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
