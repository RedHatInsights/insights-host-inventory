FROM registry.access.redhat.com/ubi9/python-312

USER 0
# use general package name instead of a specific one,
# like "postgresql-10.15-1.module+el8.3.0+8944+1ca16b1f.x86_64",
# so future security fixes are autamatically picked up.
RUN dnf install -y postgresql && \
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
COPY pytest.ini pytest.ini
COPY run_gunicorn.py run_gunicorn.py
COPY run_command.sh run_command.sh
COPY run.py run.py
RUN chown -R 1001:0 ./
USER 1001

RUN pip install "uv==0.11.11" && \
    uv sync --frozen --system

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
