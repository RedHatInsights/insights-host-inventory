FROM registry.access.redhat.com/ubi8/python-36:1-123.16099467941

USER 1001

WORKDIR /opt/app-root/src
COPY . .

RUN pip install --upgrade pip
RUN pip install pipenv
RUN pipenv install --system --dev

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
