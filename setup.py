from setuptools import find_packages, setup

if __name__ == "__main__":
    setup(
        name="insights-host-inventory",
        packages=find_packages(),
        install_requires=[
            "flask",
            "jsonify",
            "flask-restful",
            "flask-script",
            "flask-api",
            "flask-sqlalchemy",
            "psycopg2-binary",
            "flask-migrate",
            "itsdangerous",
            "request",
            "gunicorn",
            "connexion[swagger-ui]",
            "pyyaml>=3.13",
            "prometheus-client",
            "logstash-formatter",
            "pytest",
            "validators",
            "marshmallow",
            "ujson",
            "watchtower",
            "boto3",
            "kafka",
        ],
        extras_require={"tests": ["coverage", "flake8", "pytest", "pytest-asyncio"]},
        include_package_data=True,
    )
