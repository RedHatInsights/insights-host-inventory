# UBI10 does not publish a python-312 S2I image; use full UBI10 + app Python.
FROM registry.access.redhat.com/ubi10/ubi:latest

ENV APP_ROOT=/opt/app-root/src
WORKDIR $APP_ROOT

USER 0
# PostgreSQL 16 is the default stream on RHEL/UBI 10 (no modules).
RUN dnf install -y postgresql python3.14 python3.14-pip && \
    ln -sf /usr/bin/python3.14 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.14 /usr/bin/python && \
    dnf clean all

COPY api/ api/
COPY app/ app/
COPY lib/ lib/
COPY migrations/ migrations/
COPY swagger/ swagger/
COPY tests/ tests/
COPY utils/ utils/
COPY jobs/ jobs/
COPY Makefile Makefile
COPY gunicorn.conf.py gunicorn.conf.py
COPY wait_for_migrations.py wait_for_migrations.py
COPY inv_mq_service.py inv_mq_service.py
COPY inv_export_service.py inv_export_service.py
COPY logconfig.yaml logconfig.yaml
COPY manage.py manage.py
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock
COPY uv-build-version uv-build-version
COPY scripts/get_uv_pip_specifier.py scripts/get_uv_pip_specifier.py
COPY pytest.ini pytest.ini
COPY run_gunicorn.py run_gunicorn.py
COPY run_command.sh run_command.sh
COPY run.py run.py
RUN chown -R 1001:0 ./
USER 1001

ENV PATH="$APP_ROOT/.venv/bin:$PATH"

RUN UV_SPEC=$(python3 scripts/get_uv_pip_specifier.py --build-pin) && python3 -m pip install "uv${UV_SPEC}" && \
    uv sync --frozen

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
