import os
from setuptools import setup, find_packages

setup(
    name="insights-host-inventory",
    version="0.1.0",
    description="Host-based Inventory for the Insights Platform",
    url="https://github.com/redhatinsights/insights-host-inventory",
    author="Red Hat, Inc.",
    author_email="insights@redhat.com",
    packages=find_packages(),
    install_requires=[
        "Django",
        "gunicorn",
        "psycopg2-binary",
        "drf-yasg",
        "logstash_formatter",
    ],
    extras_require={
        "develop": [
            "django-extensions",
            "django-debug-toolbar",
            "flake8",
            "black",
        ],
    },
    include_package_data=True
)
