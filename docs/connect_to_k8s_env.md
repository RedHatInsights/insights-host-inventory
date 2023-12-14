# Deploying Host Inventory and Xjoin-search to Kubernetes Namespaces.
Debugging Host Inventory code requires a database, kakfa broker, Kafka Zookeeper, Debezium Connector, and xjoin-search.  These required services are deployed to Kubernetes using [Kubernetes operators](https://www.redhat.com/en/topics/containers/what-is-a-kubernetes-operator) and [bonfire](https://github.com/RedHatInsights/bonfire).

## Kubernetes Setup
### Option 1: Minikube
1. Start 'Minikube' with the following suggested [configuration](https://minikube.sigs.k8s.io/docs/handbook/config/):
    ```bash
        - disk-size: 200GB
        - driver: kvm2
        - memory: 16384
        - cpus: 6
   ```
2. Connect to image repository for generating authentication token, which is used by bonfire for pulling images from image repository:
    ```bash
        docker/podmin login -u <usrename> quay.io
    ```
3. Clone the [xjoin-operator](https://github.com/RedHatInsights/xjoin-operator) code repository and `cd` into the `xjoin-operator` directory.
4. Deplopy host-inventory:
    ```bash
        ./dev/setup-clowder.sh
    ```
5. Install CRDs:
    ```bash
        make install
    ```
6. Run the xjoin-operator:
    ```bash
        make run ENABLE_WEBHOOKS=false
    ```
7. Create a new xjoin pipeline:
    ```bash
        kubectl apply -f ./config/samples/xjoin_v1alpha1_xjoinpipeline.yaml -n test
    ```
### Option 2: Ephemeral Cluster
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
## Connecting Local Host-Inventory to Kubernetes Setup
1. In the host-inventory project directory, run:
    ```bash
        pipenv install --dev
        pipenv shell
    ```
2. Get Kafka broker address:
    ```bash
        make run_inv_mq_service_test_producer
    ```
    The `make` command complains that the kafka broker is not available and should provide the address, which should look like `env-ephemeral-spxayh-509fc239-kafka-0.env-ephemeral-spxayh-509fc239-kafka-brokers.ephemeral-spxayh.svc`
3. Add the Kafka broker address to your local `/etc/hosts` file
    ```bash
        127.0.0.1 env-ephemeral-spxayh-509fc239-kafka-0.env-ephemeral-spxayh-509fc239-kafka-brokers.ephemeral-spxayh.svc
    ```
4. To connect to database and elasticsearch pods, get credentials by downloading the [get_credentials.sh](https://github.com/RedHatInsights/xjoin-operator/blob/master/dev/get_credentials.sh) script and running:
    ```bash
        get_credentials.sh <namespace>
    ```
    get_credentials provides the credentials to access database and elasticsearch.
5. Create a new host by running:
    ```bash
        make run_inv_mq_service_test_producer
    ```
6. Verify the newly created host is available:
    ```bash
        curl --location 'http://localhost:8000/api/inventory/v1/hosts' \
             --header 'x-rh-identity: <base64-encoded idenity>' \
             --header 'Content-Type: application/json' \
             --header 'x-rh-cloud-bulk-query-source: xjoin'
    ```
    Though API GET is used, the host has been provided by `xjoin-search` which gets it from `elasticsearch` index.
7. To get hosts directly from the Elasticsearch index, run:
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
