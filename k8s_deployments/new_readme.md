# Steps for Deploying Host Inventory using Clowder

These instructions have been written on MacBookProc and may differ slightly from Fedora/RHEL

Install bonfire on the dev machine
<!-- Run "minikube start --cpus 4 --disk-size 36GB --memory 8000MB --driver=hyperkit --addons=registry --insecure-registry "10.0.0.0/24" -->
<!-- Run "minikube start --driver=hyperkit --addons=registry --insecure-registry "10.0.0.0/24" -->
1.  Start `minikube` cluster:
```
  "minikube start --addons=registry --insecure-registry "10.0.0.0/24"
```
2. Run `minikube ip` and notedown the IP address from the output.
3.  Configure Docker Daemon to use insecure-registry as shown below, where `192.168.64.27` was the output of `minikube ip`:
```
    {"debug":true,"experimental":false,"insecure-registries":["127.0.0.1:5000","192.168.64.27:5000"]}
```
4.  Create a namespace for host-inventory, e.g. "hbi":
```
    minikube kubectl -- create namespace hbi
```
5.  Set the new namespace as the default namespace and verify.
```
    kubectl config set-context $(kubectl config current-context) --namespace=hbi
    kubectl config view --minify=true | grep namespace
```
6.  Install strimzi operator for deploying `kafka`, `zookeeper`, and `minio` (TODO: Verify minio):
  A. If using `Linux`, run:
  ```
  curl -sS https://github.com/RedHatInsights/clowder/blob/master/build/kube_setup.sh | bash -
  ```
  B. If using `Mac`, first download `kube_setup.sh` and first add `''` to the `sed` command to update the namespace name and then run `kube_setup.sh`.
  ```
  sed -i '' "s/namespace: .*/namespace: ${STRIMZI_OPERATOR_NS}/" *RoleBinding*.yaml
  ```
 by downloading 'kube_setup.sh' updating the `sed` statement to use `-e`.
Install clowder to local environment:
  wget https://github.com/RedHatInsights/clowder/releases/download/0.12.0/clowder-manifest-0.12.0.yaml
  minikube kubectl -- apply -f clowder-manifest-0.12.0.yaml --validate=false
Create HBI namespace.
  minikube kubectl -- create namespace hbi
Set the new namespace as the default namespace.
  kubectl config set-context $(kubectl config current-context) --namespace=hbi
  kubectl config view --minify=true | grep namespace
To create ClowdEnvironment, download  https://github.com/RedHatInsights/clowder/blob/master/docs/examples/clowdenv.yml
Set the environment name "metadata > name: env-hbi" and "spec > targetNamespace: hbi"
Create ClowdEnvironment:
  kubectl get clowdenvironment -o yaml
Switch to insights-host-inventory repository

# ================= April 21, 2021 =================
minikube start --cpus 4 --disk-size 36GB --memory 8000MB --driver=hyperkit --addons=registry --insecure-registry "10.0.0.0/24"

# =======================================
kafka command from the minikube tutorial

kubectl -n kafka run kafka-producer -ti --image=quay.io/strimzi/kafka:0.22.1-kafka-2.7.0 --rm=true --restart=Never -- bin/kafka-console-producer.sh --broker-list my-cluster-kafka-bootstrap:9092 --topic my-topic

kubectl -n kafka run kafka-producer -ti --image=quay.io/strimzi/kafka:0.22.1-kafka-2.7.0 --rm=true --restart=Never -- bin/kafka-console-producer.sh --broker-list my-cluster-kafka-bootstrap:9092 --topic my-topic

# ========= create secret for getting imgaes from quay =========
kubectl create secret docker-registry quay --docker-server=quay.io --docker-username=thearifismail --docker-password=insights --docker-email=arifismail@yahoo.com



===========
Deploy postgres db deployment
kubectl create deployment inventory-db --image=`127.0.0.1:5000/postgres

https://medium.com/@xcoulon/deploying-your-first-web-app-on-minikube-6e98d2884b3a
---
aarif@MacBook-Pro~/Documents/dev-ws/insights/insights-host-inventory[hbi_clowder*] $ kubectl logs inventory-db-777cf645dd-jt465
Error: Database is uninitialized and superuser password is not specified.
       You must specify POSTGRES_PASSWORD to a non-empty value for the
       superuser. For example, "-e POSTGRES_PASSWORD=password" on "docker run".

       You may also use "POSTGRES_HOST_AUTH_METHOD=trust" to allow all
       connections without a password. This is *not* recommended.

       See PostgreSQL documentation about "trust":
       https://www.postgresql.org/docs/current/auth-trust.html
aarif@MacBook-Pro~/Documents/dev-ws/insights/insights-host-inventory[hbi_clowder*] $

=====
(app-root) sh-4.4$ pytest
Traceback (most recent call last):
  File "/opt/app-root/bin/pytest", line 5, in <module>
    from pytest import main
  File "/opt/app-root/lib64/python3.8/site-packages/pytest.py", line 7, in <module>
    from _pytest.config import cmdline
  File "/opt/app-root/lib64/python3.8/site-packages/_pytest/config/__init__.py", line 12, in <module>
    import importlib_metadata
ModuleNotFoundError: No module named 'importlib_metadata'
(app-root) sh-4.4$ pip install importlib_metadata
Collecting importlib_metadata
  Downloading importlib_metadata-4.0.1-py3-none-any.whl (16 kB)
Requirement already satisfied: zipp>=0.5 in /opt/app-root/lib/python3.8/site-packages (from importlib_metadata) (3.4.1)
Installing collected packages: importlib-metadata
Successfully installed importlib-metadata-4.0.1
(app-root) sh-4.4$
(app-root) sh-4.4$
(app-root) sh-4.4$
(app-root) sh-4.4$


oc describe po env-hbi-kafka-5586985c9c-9ctmv
    Environment:
      KAFKA_ADVERTISED_LISTENERS:              PLAINTEXT://env-hbi-kafka.hbi.svc:29092, LOCAL://localhost:9092
      KAFKA_BROKER_ID:                         1
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR:  1
      KAFKA_ZOOKEEPER_CONNECT:                 env-hbi-zookeeper:32181
      LOG_DIR:                                 /var/lib/kafka
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP:    PLAINTEXT:PLAINTEXT, LOCAL:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME:        LOCAL

oc describe po env-hbi-zookeeper-668dd5b7b-hxklb
    Environment:
      ZOOKEEPER_INIT_LIMIT:   10
      ZOOKEEPER_CLIENT_PORT:  32181
      ZOOKEEPER_SERVER_ID:    1
      ZOOKEEPER_SERVERS:      env-hbi-zookeeper:32181
      ZOOKEEPER_TICK_TIME:    2000
      ZOOKEEPER_SYNC_LIMIT:   10
(insights-host-inventory) aarif@MacBook-Pro~/Documents/dev-ws/insights/insights-host-inventory[hbi_docker_compose] $
