FROM registry.access.redhat.com/ubi9/python-39

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
COPY host_reaper.py host_reaper.py
COPY host_synchronizer.py host_synchronizer.py
COPY inv_mq_service.py inv_mq_service.py
COPY inv_export_service.py inv_export_service.py
COPY logconfig.yaml logconfig.yaml
COPY manage.py manage.py
COPY pendo_syncher.py pendo_syncher.py
COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock
COPY pytest.ini pytest.ini
COPY rebuild_events_topic.py rebuild_events_topic.py
COPY run_gunicorn.py run_gunicorn.py
COPY run_command.sh run_command.sh
COPY run.py run.py
COPY system_profile_validator.py system_profile_validator.py
COPY generate_stale_host_notifications.py generate_stale_host_notifications.py
COPY create_ungrouped_host_groups.py create_ungrouped_host_groups.py
COPY delete_ungrouped_host_groups.py delete_ungrouped_host_groups.py
COPY assign_ungrouped_hosts_to_groups.py assign_ungrouped_hosts_to_groups.py
COPY export_group_data_s3.py export_group_data_s3.py
COPY update_hosts_last_check_in.py update_hosts_last_check_in.py
COPY update_edge_hosts_prs.py update_edge_hosts_prs.py
RUN chown -R 1001:0 ./
USER 1001

# Set pipenv to version 2022.4.8 to prevent pip from updating and
# failing a rootless image build
RUN pip install pipenv==2022.4.8  && \
    pipenv install --system --dev

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
