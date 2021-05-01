FROM registry.access.redhat.com/ubi8/python-38:1-54.1618436884

USER root

# set the subscription-manager password before running
# RUN subscription-manager register --username=theaarif --password=<password> registration.log
RUN dnf install -y postgresql-10.15-1.module+el8.3.0+8944+1ca16b1f.x86_64

USER 1001

WORKDIR /opt/app-root/src

COPY . .

# move all pip installs to one line
RUN pip install --upgrade pip
RUN pip install pipenv
RUN pipenv install --system --dev

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
