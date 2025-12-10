# Debugging Local Code with Services Deployed into Kubernetes Namespaces

This guide covers debugging Host Based Inventory code that runs locally while connecting to services deployed in Kubernetes (Minikube or Ephemeral cluster). This setup requires database, Kafka broker, Kafka Zookeeper, Debezium Connector, and RBAC services.

## Prerequisites

- Kubernetes cluster (Ephemeral or Minikube) with access credentials
- [bonfire](https://github.com/RedHatInsights/bonfire) installed for deploying services
- VS Code with Python debugging capabilities
- Access to the host-inventory codebase

## Kubernetes Setup

### Option 1: Ephemeral Cluster (Recommended)

1. **Login to Ephemeral cluster:**
   ```bash
   oc login <ephemeral-cluster-url>
   ```

2. **Reserve a namespace:**
   ```bash
   bonfire namespace reserve -d xxh  # where xx is the number of hours, e.g 8h. The default reservation time is one hour
   ```

3. **Deploy host-inventory and RBAC:**

   The `RBAC V2` options may be omitted to use `RBAC V1`.

   ```bash
   bonfire deploy host-inventory \
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

4. **Expose service ports:**

   Download the [set_hbi_rbac_ports.sh](set_hbi_rbac_ports.sh) script and run:
   ```bash
   set_hbi_rbac_ports.sh <namespace>
   ```

5. **Get database credentials:**

   Download the [get_hbi_rbac_db_creds.sh](get_hbi_rbac_db_creds.sh) script and run:
   ```bash
   get_hbi_rbac_db_creds.sh <namespace>
   ```

   This provides the credentials needed to access the database.

### Option 2: Minikube (INCOMPLETE)

1. **Start Minikube with the following configuration:**
   ```bash
   minikube start \
       --disk-size=200GB \
       --driver=kvm2 \
       --memory=16384 \
       --cpus=6
   ```

2. **Connect to image repository:**
   ```bash
   docker/podman login -u <username> quay.io
   ```

3. **Use bonfire to install host-inventory:**
   - Clone the [xjoin-operator](https://github.com/RedHatInsights/xjoin-operator) repository
   - Install CRDs: `make install`
   - Deploy host-inventory using bonfire (may require installing additional CRDs)

## Connecting Local Code to Kubernetes Setup

1. **Install dependencies:**
   ```bash
   cd insights-host-inventory
   pipenv install --dev
   pipenv shell
   ```

2. **Get Kafka broker address:**
   ```bash
   make run_inv_mq_service_test_producer
   ```

   The command will fail with an error providing the Kafka broker address, which should look like:
   ```
   env-ephemeral-spxayh-509fc239-kafka-0.env-ephemeral-spxayh-509fc239-kafka-brokers.ephemeral-spxayh.svc
   ```

3. **Add Kafka broker address to `/etc/hosts`:**
   ```bash
   sudo echo "127.0.0.1 env-ephemeral-spxayh-509fc239-kafka-0.env-ephemeral-spxayh-509fc239-kafka-brokers.ephemeral-spxayh.svc" >> /etc/hosts
   ```

4. **Test the connection by creating a host:**
   ```bash
   make run_inv_mq_service_test_producer
   ```

5. **Verify the host was created:**
   ```bash
   curl --location 'http://localhost:8000/api/inventory/v1/hosts' \
        --header 'x-rh-identity: <base64-encoded identity>' \
        --header 'Content-Type: application/json'
   ```

## Debugging API Code with VS Code

This section describes how to debug the API server locally while it connects to resources deployed in the Kubernetes namespace.

1. **Load the project in VS Code:**
   ```bash
   code insights-host-inventory
   ```

2. **Create or update `.vscode/launch.json` with the following configuration:**
   ```json
   {
       "version": "0.2.0",
       "configurations": [
           {
               "name": "Python: Inventory API Debug",
               "type": "python",
               "request": "launch",
               "program": "run.py",
               "console": "integratedTerminal",
               "justMyCode": false,
               "env": {
                   "BYPASS_RBAC": "true",
                   "BYPASS_UNLEASH": "true",
                   "BYPASS_KESSEL": "true",
                   "INVENTORY_DB_USER": "<user from get_hbi_rbac_db_creds>",
                   "INVENTORY_DB_PASS": "<password from get_hbi_rbac_db_creds>",
                   "INVENTORY_DB_NAME": "<db name from get_hbi_rbac_db_creds>",
                   "INVENTORY_DB_HOST": "localhost",
                   "INVENTORY_DB_POOL_TIMEOUT": "5",
                   "INVENTORY_DB_POOL_SIZE": "5",
                   "KAFKA_BOOTSTRAP_SERVERS": "localhost:29092",
                   "KAFKA_EVENT_TOPIC": "platform.inventory.events",
                   "PROMETHEUS_MULTIPROC_DIR": "./temp/PROMETHEUS_MULTIPROC_DIR/",
                   "FLASK_ENV": "development",
                   "FLASK_DEBUG": "1"
               }
           }
       ]
   }
   ```

3. **Launch the API server:**
   - Set breakpoints in your code as needed
   - Press F5 or click "Start Debugging"
   - The API server will start on a port different from the host-inventory-service running in Kubernetes

4. **Test with curl:**
   ```bash
   curl --location 'http://localhost:8000/api/inventory/v1/hosts' \
        --header 'x-rh-identity: <base64-encoded identity>' \
        --header 'Content-Type: application/json'
   ```

## Debugging MQ Service

Debugging the MQ service requires stopping the service running in Kubernetes and running it locally. Since services are managed by Kubernetes operators with auto-reconciliation, you need to disable it temporarily.

### Disable Auto-Reconciliation

1. **Turn off auto-reconciliation:**
   ```bash
   kubectl edit clowdenvironment <env-name> -n <namespace>
   ```

2. **Add the following under `spec`:**
   ```yaml
   spec:
       disabled: true
   ```

3. **Stop the MQ service pods:**
   ```bash
   kubectl edit deployment host-inventory-mq-p1 -n <namespace>
   ```

   In the editor, find `replicas: 1` and change it to `replicas: 0`.

   If there are more MQ services (e.g., host-inventory-mq-p2), stop them also:
   ```bash
   kubectl edit deployment host-inventory-mq-p2 -n <namespace>
   # Change replicas to 0
   ```

4. **Verify the pods are stopped:**
   ```bash
   kubectl get po -n <namespace> | grep host-inventory-mq
   ```
   The output should show no MQ pods running.

### Debug the MQ Service Locally

1. **Create a VS Code launch configuration for MQ service:**

   Add this to `.vscode/launch.json`:
   ```json
   {
       "name": "Python: Inventory MQ Service Debug",
       "type": "python",
       "request": "launch",
       "program": "inv_mq_service.py",
       "console": "integratedTerminal",
       "justMyCode": false,
       "env": {
           "BYPASS_RBAC": "true",
           "BYPASS_UNLEASH": "true",
           "BYPASS_KESSEL": "true",
           "INVENTORY_DB_USER": "<user from get_hbi_rbac_db_creds>",
           "INVENTORY_DB_PASS": "<password from get_hbi_rbac_db_creds>",
           "INVENTORY_DB_NAME": "<db name from get_hbi_rbac_db_creds>",
           "INVENTORY_DB_HOST": "localhost",
           "KAFKA_BOOTSTRAP_SERVERS": "localhost:29092",
           "KAFKA_EVENT_TOPIC": "platform.inventory.events"
       }
   }
   ```

2. **Start the debugger:**
   - Set breakpoints in the MQ service code (e.g., in `./app/queue/queue.py` in the `handle-message` function)
   - Press F5 or start the debugger with the MQ Service configuration

3. **Create a host to trigger the breakpoint:**
   In a new terminal:
   ```bash
   pipenv shell
   make run_inv_mq_service_test_producer
   ```

   The debugger should stop at the breakpoint you set.

### Re-enable Auto-Reconciliation

When you're done debugging, restore the Kubernetes services:

1. **Enable auto-reconciliation:**
   ```bash
   kubectl edit clowdenvironment <env-name> -n <namespace>
   ```

   Change `disabled: true` to `disabled: false` in the spec section.

2. **The operator will automatically restart the MQ service pods.**

## Cleanup

When you're done debugging and want to clean up resources:

1. **If using an ephemeral namespace:**
   ```bash
   bonfire namespace release -n <namespace>
   ```

2. **Remove the Kafka broker entry from `/etc/hosts`:**
   Edit `/etc/hosts` and remove the line you added for the Kafka broker.

## Troubleshooting

### Kafka Connection Issues
- Verify the Kafka broker address is correctly added to `/etc/hosts`
- Check that port forwarding is active: `kubectl get svc -n <namespace>`

### Database Connection Issues
- Verify you have the correct credentials from `get_hbi_rbac_db_creds`
- Check that the database port is forwarded correctly

### Debugger Not Starting
- Ensure you're in the pipenv shell when launching from terminal
- Check that all required environment variables are set in the launch configuration
- Verify the Python path in VS Code points to the pipenv virtual environment

### Services Keep Restarting
- Ensure auto-reconciliation is properly disabled
- Check that you edited the ClowdEnvironment resource, not just the deployment
