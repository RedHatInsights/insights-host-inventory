#!/usr/bin/env bash

NAMESPACE=`oc project -q 2>/dev/null || true`
RBAC_SERVICE_POD=$(oc get pods -l pod=rbac-service -o json | jq -r '.items[] | select(.status.phase == "Running" and .metadata.deletionTimestamp == null) | .metadata.name' | head -n 1)

USER_FILE="./data/rbac_users_data.json"
# --- Check if the JSON file exists ---
if [ ! -f "$USER_FILE" ]; then
  echo "Error: JSON file '$USER_FILE' not found."
  exit 1
fi

# USER_IDs=$(cat "$RBAC_FILE" | jq -r '.grou')

ORG_ID_LIST=($(jq -r '.[].attributes.org_id' "$USER_FILE"  | tr -d '[]," '))
IS_ORG_ADMIN_LIST=($(jq -r '.[].attributes.is_org_admin' "$USER_FILE"  | tr -d '[]," '))
USER_NAME_LIST=($(jq -r '.[].username' "$USER_FILE"  | tr -d '[]," '))
USER_ID_LIST=($(jq -r '.[].attributes.user_id' "$USER_FILE"  | tr -d '[]," '))


# get the number of users
num_users=${#USER_ID_LIST[@]}

# Batch requset format
# batch = [(<org_id>, <is_admin>, <user_name>, <user_id>)]

# Add the default user "jdoe" to the batch list manually
# Note: jdoe is bootstrapped in ephemeral and wont be in our users list

batch_item+="["
batch_item+="(\"12345\", True, \"jdoe\", \"12345\"),"

# Add users
for (( i=0; i<${num_users}; i++ ));
do
  is_org_Admin=$(echo ${IS_ORG_ADMIN_LIST[i]} | awk '{print toupper(substr($0,0,1))tolower(substr($0,2))}')
  batch_item+="(\"${ORG_ID_LIST[$i]}\",$is_org_Admin,\"${USER_NAME_LIST[i]}\",\"${USER_ID_LIST[i]}\")"
  if (($i < $((num_users-1)) )); then
    batch_item+=","
  fi
  if (($i == $((num_users-1)))); then
    batch_item+="]"
  fi
  batch+=$batch_item
  batch_item=""
done

echo "Processing batch request for: "$batch

while true; do
  # Send the Batch request to RBAC service pod to get the users into RBAC and replicate them to relations
  oc exec -it $RBAC_SERVICE_POD --container=rbac-service -- /bin/bash -c "./rbac/manage.py shell << EOF
from management.management.commands.utils import process_batch
process_batch($batch)
exit()
EOF"
  EXIT_STATUS=$?
  if [ $EXIT_STATUS -ne 0 ]; then
      echo "Rbac service pod was OOMKilled or was otherwise unavailable when attempting to run the user seed script. Trying again..."
      oc rollout status deployment/rbac-service -w
      RBAC_SERVICE_POD=$(oc get pods -l pod=rbac-service -o json | jq -r '.items[] | select(.status.phase == "Running" and .metadata.deletionTimestamp == null) | .metadata.name' | head -n 1)
    else
      break
    fi
done

## Adding users to management_principal table in RBAC
# Tenants are bootstrapped from the process_batch() above
# Get the tenant ID and parse the users list (json) and insert into the DB, This will avoid the need for logging in Via console
RBAC_DB_POD=$(oc get pods -l app=rbac,service=db,sub=local_db --no-headers -o custom-columns=":metadata.name" --field-selector=status.phase==Running | head -1)

# Add the default user "jdoe" to RBAC managment_ principal table
UUID=$(uuidgen | tr "[:upper:]" "[:lower:]")
RBAC_TENANT_ID=$(oc exec "$RBAC_DB_POD" -- psql -d rbac -t -c "select id from api_tenant where org_id='12345';" | head -1 | tr -d '[:space:]')
RESULT=$(oc exec "$RBAC_DB_POD" -- psql -d rbac -t -c "Insert INTO management_principal (uuid, username,tenant_id,type,user_id) VALUES ('$UUID','jdoe','$RBAC_TENANT_ID','user','12345');")

# Add users from the JSON file to RBAC Principals table
for (( i=0; i<${num_users}; i++ ));
do
#    This can be avoided if we can verify
  UUID=$(uuidgen | tr "[:upper:]" "[:lower:]")
  ORG_ID=${ORG_ID_LIST[$i]}
  echo "Adding user :"${USER_NAME_LIST[i]} "from Org:" $ORG_ID "to RBAC"
  RBAC_TENANT_ID=$(oc exec "$RBAC_DB_POD" -- psql -d rbac -t -c "select id from api_tenant where org_id='$ORG_ID';" | head -1 | tr -d '[:space:]')
  RESULT=$(oc exec "$RBAC_DB_POD" -- psql -d rbac -t -c "Insert INTO management_principal (uuid, username,tenant_id,type,user_id) VALUES ('$UUID','${USER_NAME_LIST[i]}','$RBAC_TENANT_ID','user','${USER_ID_LIST[i]}');")
  echo $RESULT
done
