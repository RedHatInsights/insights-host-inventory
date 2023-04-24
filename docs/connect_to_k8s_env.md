# Deploy Host Inventory to a Kubernetes Namespace in Ephemeral Cluster
Debugging the Host Inventory API code needs database, kakfa broker, Kafka Zookeeper, Debezium Connector, and xjoin-search. Following is a list of high level steps necessary to debug local API code using an Ephemeral namespace. The steps are the same for resources running in minikube.

1. Login to Ephemeral cluster.
2. Reserve a namespace:
    ```bash
        bonfire namespace reserve -d xxh    # the default reservation time is one hour
   ```
3. Deploy host-inventory:
    ```bash
        bonfire deploy host-inventory -n <namespace>
    ```
4. Exposed service ports by downloading the [forward-ports-clowder.sh](https://github.com/RedHatInsights/xjoin-operator/blob/master/dev/forward-ports-clowder.sh) script and running:
    ```bash
        forward-ports-clowder.sh <namespace>
    ```
5. In the host-inventory project directory, run:
    ```bash
        pipenv install --dev
        pipenv shell
    ```
6. Get Kafka broker address:
    ```bash
        make run_inv_mq_service_test_producer
    ```
    The `make` command complains that the kafka broker is not available and should provide the address, which should look like `env-ephemeral-spxayh-509fc239-kafka-0.env-ephemeral-spxayh-509fc239-kafka-brokers.ephemeral-spxayh.svc`
7. Add the Kafka broker address to your local `/etc/hosts` file
    ```bash
        127.0.0.1 env-ephemeral-spxayh-509fc239-kafka-0.env-ephemeral-spxayh-509fc239-kafka-brokers.ephemeral-spxayh.svc
    ```
8. To connect to database and elasticsearch pods, get credentials by downloading the [get_credentials.sh](https://github.com/RedHatInsights/xjoin-operator/blob/master/dev/get_credentials.sh) script and running:
    ```bash
        get_credentials.sh <namespace>
    ```
    get_credentials provides the credentials to access database and elasticsearch.
9. Create a new host by running:
    ```bash
        make run_inv_mq_service_test_producer
    ```
10. Verify the newly created host is available:
    ```bash
        curl --location 'http://localhost:8000/api/inventory/v1/hosts' \
             --header 'x-rh-identity: <base64-encoded idenity>' \
             --header 'Content-Type: application/json' \
             --header 'x-rh-cloud-bulk-query-source: xjoin'
    ```
    Though API GET is used, the host has been provided by `xjoin-search` which gets it from `elasticsearch` index.
11. To get hosts directly from the Elasticsearch index, run:
    ```bash
        curl --location 'http://localhost:9200/xjoin.inventory.hosts/_search' \
             --header 'Authorization: Basic <elastic-user value from get_credentials>='
    ```
    Note: index name, "xjoin.inventory.hosts" may be different in your case.

# Setup Development environment for Debugging API Code
This section describes how to launch debugger using `VS Code` to execute the local API server which in turn uses resources deployed in the ephemeral namespace.
1. Load the `host-inventory` project to VS Code
2. Add a launch configuration to run the api-server `run.py` with the following environment variables:
    ```bash
    {
        "version": "0.2.0",
        "configurations": [
            {
                "name": "Python: Current File",
                "type": "python",
                "request": "launch",
                "program": "run.py",
                "console": "integratedTerminal",
                "justMyCode": false,
                "env": {
                    "BYPASS_RBAC": "true",
                    "INVENTORY_DB_USER": "<user provided get_credentials>",
                    "INVENTORY_DB_PASS": "<password provided get_credentials>",
                    "INVENTORY_DB_NAME": "<DB name provided get_credentials>",
                    "PROMETHEUS_MULTIPROC_DIR": "./temp/prometheus_multiproc_dir/",
                    "prometheus_multiproc_dir": "./temp/prometheus_multiproc_dir/",
                    "FLASK_ENV": "development"
                },
            },
        ]
    }
    ```
3. Launch the api-server on a port different from the one used by the host-inventory-service
4. Use the `curl` statements provided above to debug and step through the local code.
