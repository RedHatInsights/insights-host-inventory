# Deploying Host Inventory to Kubernetes Namespaces.
Debugging Host Inventory code requires a database, Kakfa broker, Kafka Zookeeper, Debezium Connector, and RBAC.  These required services are deployed to Ephemeral cluster using [bonfire](https://github.com/RedHatInsights/bonfire).

## Kubernetes Setup
### Option 1: Ephemeral Cluster
1. Login to Ephemeral cluster.
2. Reserve a namespace:
    ```bash
        bonfire namespace reserve -d xxh    # where xx is the number of hours, e.g 8h. The default reservation time is one hour
   ```
3. Deploy host-inventory and RBAC using the following command.  The `RBAC V2` options may be omitted to use `RBAC V1`.
    ```bash
        bonfire deploy host-inventory \
            --set-parameter host-inventory/RBAC_V2_FORCE_ORG_ADMIN=true \
            --set-parameter host-inventory/CONSUMER_MQ_BROKER=rbac-kafka-kafka-bootstrap:9092 \
            --ref-env insights-stage \
            --set-image-tag quay.io/cloudservices/insights-inventory=latest \
            --set-image-tag quay.io/cloudservices/rbac=latest \
            --set-parameter host-inventory/BYPASS_RBAC=false \
            -p rbac/V2_APIS_ENABLED=True \
            -p rbac/V2_READ_ONLY_API_MODE=False \
            -p rbac/V2_BOOTSTRAP_TENANT=True \
            -p rbac/REPLICATION_TO_RELATION_ENABLED=True \
            -n $(oc project --short)
    ```
4. Expose service ports by downloading the [set_hbi_rbac_ports.sh](set_hbi_rbac_ports.sh) script and running:
    ```bash
        set_hbi_rbac_ports.sh <namespace>
5. To connect to database, get credentials by downloading the [get_hbi_rbac_db_creds](./get_hbi_rbac_db_creds.sh) script and running:
    ```bash
        get_hbi_rbac_db_creds.sh <namespace>
    ```

### Option 2: Minikube (INCOMPLETE)
1. Start 'Minikube' with the following suggested [configuration](https://minikube.sigs.k8s.io/docs/handbook/config/):
    ```bash
        - disk-size: 200GB
        - driver: kvm2
        - memory: 16384
        - cpus: 6
   ```
2. Connect to image repository for generating authentication token, which is used by bonfire for pulling images from image repository:
    ```bash
        docker/podman login -u <username> quay.io
    ```
3. Use bonfire to install host-inventory.  May require installing the CRDs needed.

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
    The `make` command complains that the Kafka broker is not available and should provide the address, which should look like `env-ephemeral-spxayh-509fc239-kafka-0.env-ephemeral-spxayh-509fc239-kafka-brokers.ephemeral-spxayh.svc`
3. Add the Kafka broker address to your local `/etc/hosts` file
    ```bash
        127.0.0.1 env-ephemeral-spxayh-509fc239-kafka-0.env-ephemeral-spxayh-509fc239-kafka-brokers.ephemeral-spxayh.svc
    ```
4. Create a new host by running:
    ```bash
        make run_inv_mq_service_test_producer
    ```
5. Verify the newly created host is available:
    ```bash
        curl --location 'http://localhost:8000/api/inventory/v1/hosts' \
             --header 'x-rh-identity: <base64-encoded identity>' \
             --header 'Content-Type: application/json'
    ```

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
                    "INVENTORY_DB_USER": "<user provided get_credentials>",
                    "INVENTORY_DB_PASS": "<password provided get_credentials>",
                    "INVENTORY_DB_NAME": "<DB name provided get_credentials>",
                    "FLASK_ENV": "development"
                },
            },
        ]
    }
    ```
3. Launch the api-server on a port different from the one used by the host-inventory-service
4. Use the `curl` statements provided above to debug and step through the local code.
