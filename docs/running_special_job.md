# Running a Special Job
A recent update to the Hosts table in the Host-Inventory database required updating every host in the table.  Making such change was tricky for the Production deployment because it posed a chicken-and-egg problem.  The update could be made by executing a job created by a new ClowdJobInvocation (CJI) using a special image that is different from the current image. The problem was that the ClowdApp operator did not allow CJIs to use a different image than the one used by the parent/main clowdapp, host-inventory, and that is the reason for this document.

The problem was solved by hard-coding the new image in a new CJI definition in the [Clowdapp template](https://github.com/RedHatInsights/insights-host-inventory/blob/f12eeec16cda33d9e90dfdcd2999deb2bb03604f/deploy/clowdapp.yml#L630) and then updating the [SaaS file](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/deploy-clowder.yml) to explicitly use an [IMAGE_TAG](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/deploy-clowder.yml#L99) for deploying the parent clowdapp, host-inventory.

## Steps
1.  Create new image as required. e.g. quay.io/cloudservices/insights-inventory:bca5615
    ```bash
    - name: just-host-synchronizer
      podSpec:
        image: quay.io/cloudservices/insights-inventory:bca5615
        restartPolicy: OnFailure
        command:
          - /bin/sh
          - -c
          - python host_synchronizer.py
        env:
          - name: INVENTORY_LOG_LEVEL
            value: ${LOG_LEVEL}
    ```
2.  Update the [ClowdJobInvocation definition file](../deploy/cji.yml#L15) to use the new job name, `just-host-synchronizer`.
    ```bash
        apiVersion: v1
        kind: Template
        metadata:
        name: insights-host-inventory-cjis
        objects:
        - apiVersion: cloud.redhat.com/v1alpha1
        kind: ClowdJobInvocation
        metadata:
            labels:
            app: host-inventory
            name: just-host-synchronizer-${SYNCHRONIZER_RUN_NUMBER}
        spec:
            appName: host-inventory
            jobs:
            - just-host-synchronizer
        parameters:
        - name: SYNCHRONIZER_RUN_NUMBER
        value: '1'
    ```
4.  Create a pull request to get these updates into [host-inventory](https://github.com/RedHatInsights/insights-host-inventory).
5.  From the target Kubernetes cluster, get the image tag of the currently deployed [service](https://console-openshift-console.apps.crcp01ue1.o9m8.p1.openshiftapps.com/k8s/ns/host-inventory-prod/deployments/host-inventory-service). e.g. `a873421`.  All services in host-inventory use the same image.
6.  Clone the [app-interface](https://gitlab.cee.redhat.com/service/app-interface) repo.
7.  Update the [host-inventory SAAS](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/deploy-clowder.yml) file.
    * Change the ref value of the target cluster/namespace with the commit SHA from Step 4.  For this write up, the [ref](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/deploy-clowder.yml#L97) in Production cluster was used.
    * Under `parameters`, set `IMAGE_TAG` to the one currently deployed in the target cluster, so that running the new job does not affect the current state of the application.
8.  Create a merge request (MR) to get the changes from the previous step merged.
9.  Clone the [app-interface](https://gitlab.cee.redhat.com/service/app-interface) repo again to add the new CJI.
10. Update the CJI in [host-inventory SAAS](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/deploy-clowder.yml) file to set the ref like before and the job run number in CJI definition [target cluster](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/deploy-clowder.yml#L147) in the SAAS file.
11. Create another MR to get the latest changes merged.
12. After the MR is merged, monitor the new job in a terminal window:
    * connect to the cluster and run
        ```bash
        $ kubectl get cji -n host-inventory-prod
        NAME                        COMPLETED
        events-topic-rebuilder      false
        just-host-synchronizer-15   false
        $
        ```
    * Get the pod name:
        ```bash
        kubectl get po | grep just-host-synchronizer # note job name in the pod name
        host-inventory-just-host-synchronizer-hg4rqrg-9hxh8   0/1   Running   0   10m
        ```
    * Check the log:
        ```bash
        kubectl logs host-inventory-just-host-synchronizer-hg4rqrg-9hxh8 -n host-inventory-prod
        ```
13. After the CJI completes the job execution, expect the following
    ```bash
        [aarif@damaan insights-host-inventory]$ kubectl get cji -n host-inventory-prod
        NAME                        COMPLETED
        events-topic-rebuilder      false
        just-host-synchronizer-15   true
        $
        $
        $ kubectl get po | grep just-host-synchronizer
        host-inventory-just-host-synchronizer-hg4rqrg-9hxh8   0/1   Completed   0   20h
        $
    ```
