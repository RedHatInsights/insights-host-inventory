# Debugging Local Code with Services Deployed into Kubernetes Namespaces
The instructions in this page require host-inventory and xjoin-search to be running in an Ephemeral cluster or Minikube.

Debugging local code requires stopping the same code running in Kubernetes.  However, stopping such services is tricky when the services have been deployed using Kubernetes operators and requires disabling `auto reconciliation` by the service operator.  For this write-up, `inventory-mq-service` has been used as an example.

1. Turn off `auto-reconciliation`:
    ```bash
        kubectl edit clowdenvironment <env-name>
    ```
2. In the editor, which is opened by the `kubectl edit ...` command, add the following under `spec`.
    ```
    spec:
        disabled: true
    ```
3. In `host-inventory-mq-*` pods, set the `replicas` size to `zero`:
    ```bash
        kubectl edit deployment host-inventory-mq-p1 -n <namespace>
    ```
    In the editor, find `replicas: 1` and change it to `replicas: 0`.
    If there are more `mq-services` stop them also.
    Verify that `host-inventory-mq-*` pods are NOT listed in the output of `kubectl get po -n <namespace>`
4. In `VS Code`, start `inv_mq_service.py` in debug mode and set a break point; e.g. in `./app/queue/queue.py>handle-message`.
5. Start a new terminal and go to the `insights-host-inventory` project director and run `pipenv shell` and create a host:
    ```
        pipenv shell
        make run_inv_mq_service_test_producer
    ```
    Debugger should stop at the breakpoint set above.
6.  When done debugging, simply enable auto-reconciliation by setting `disabled: false` in the clowdenvironment. 
