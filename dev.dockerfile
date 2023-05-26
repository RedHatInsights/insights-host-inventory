FROM registry.access.redhat.com/ubi8/python-39

USER 0
# use general package name instead of a specific one,
# like "postgresql-10.15-1.module+el8.3.0+8944+1ca16b1f.x86_64",
# so future security fixes are autamatically picked up.
RUN dnf install -y postgresql snappy && \
    dnf clean all

COPY . .
RUN chown -R 1001:0 ./
USER 1001

# Set pipenv to version 2022.4.8 to prevent pip from updating and
# failing a rootless image build
RUN pip install pipenv==2022.4.8  && \
    pipenv install --system --dev

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
