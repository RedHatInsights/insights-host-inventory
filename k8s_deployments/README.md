1.  Start `minikube` cluster:
```
    minikube start --cpus 4 --disk-size 36GB --memory 8000MB --driver=hyperkit --addons=registry --insecure-registry "10.0.0.0/24"
```
2.  Run 'minikube ip' and note down the IP address
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
6.  Create db deployment and service:
```
    kubectl create -f db-deployment.yaml
    kubectl create -f db-service.yaml
```
7.  Create zookeeper deployment and service:
```
    kubectl create -f zookeeper-deployment.yaml
    kubectl create -f zookeeper-service.yaml
```
7.  Create Kafka deployment:
```
    kubectl create -f kafka-deployment.yaml
    kubectl create -f kafka-service.yaml

```
7.  Create zookeeper deployment:
```

```
7.  Create zookeeper deployment:
```

```
7.  Create zookeeper deployment:
```

```
7.  Create zookeeper deployment:
```

```
