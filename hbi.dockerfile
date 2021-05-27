FROM quay.io/thearifismail/ubi8-python38-psql:latest

USER 1001

WORKDIR /opt/app-root/src
COPY . .

RUN pip install --upgrade pip && \
    pip install pipenv && \
    pipenv install --system --dev

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
