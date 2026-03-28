#!/usr/bin/env bash

# Check if jq is installed
if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is not installed. Please install jq to continue." >&2
  exit 1
fi

# Check if bonfire is installed
if ! command -v bonfire >/dev/null 2>&1; then
  echo "Error: crc-bonfire is not installed. Please install crc-bonfire to continue." >&2
  exit 1
fi

# Getting all Keycloak vars from `bonfire namespace describe` result
json_output=$(bonfire namespace describe -o json)

# Export environment variables from keys containing "keycloak_admin"
eval $(echo "$json_output" | jq -r '
  to_entries[]
  | select(.key | test("keycloak_admin"))
  | "\(.key | ascii_upcase)=\(.value | @sh)"'
)

# Get the ACCESS TOKEN from Keycloak
MASTER_REALM_NAME="master"
REALM_NAME="redhat-external"
CLIENT_ID="admin-cli"
JSON_FILE="./data/rbac_users_data.json"

TOKEN_RESPONSE=$(curl -s -X POST \
  "${KEYCLOAK_ADMIN_ROUTE}/realms/${MASTER_REALM_NAME}/protocol/openid-connect/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "scope=openid&grant_type=password&username=${KEYCLOAK_ADMIN_USERNAME}&password=${KEYCLOAK_ADMIN_PASSWORD}&client_id=${CLIENT_ID}")

if [ $? -ne 0 ]; then
  echo "Error fetching access token."
  echo "$TOKEN_RESPONSE"
  exit 1
fi

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')

if [ -z "$ACCESS_TOKEN" ]; then
  echo "Failed to extract access token."
  echo "$TOKEN_RESPONSE"
  exit 1
fi

echo "Successfully obtained Access Token."
# echo "ACCESS_TOKEN: $ACCESS_TOKEN"

# --- Check if the JSON file exists ---
if [ ! -f "$JSON_FILE" ]; then
  echo "Error: JSON file '$JSON_FILE' not found."
  exit 1
fi

USERS=$(cat "$JSON_FILE")

if [[ "${USERS:0:1}" != "[" ]]; then
  echo "Error: The JSON file does not contain a top-level array of user objects."
  exit 1
fi

echo "$USERS" | jq -c '.[]' | while IFS= read -r USER_JSON; do
  echo "Creating user: $(echo "$USER_JSON" | jq -r '.username')"

  CREATE_USER_RESPONSE=$(curl -s -X POST \
    "${KEYCLOAK_ADMIN_ROUTE}/admin/realms/${REALM_NAME}/users" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$USER_JSON")

  HTTP_CODE=$?

  if [ "$HTTP_CODE" -eq 0 ]; then
    if echo "$CREATE_USER_RESPONSE" | jq -e '.id'; then
      echo "User '$(echo "$USER_JSON" | jq -r '.username')' created successfully."
      USER_ID=$(echo "$CREATE_USER_RESPONSE" | jq -r '.id')
      echo "User ID: $USER_ID"
    elif echo "$CREATE_USER_RESPONSE" | jq -e '.errorMessage'; then
      echo "Error creating user '$(echo "$USER_JSON" | jq -r '.username')' (from Keycloak response):"
      echo "$CREATE_USER_RESPONSE" | jq -r '.errorMessage'
    elif echo "$CREATE_USER_RESPONSE" | grep -q "already exists"; then
      echo "User '$(echo "$USER_JSON" | jq -r '.username')' already exists."
    else
      echo "Request for user '$(echo "$USER_JSON" | jq -r '.username')' successful, but unable to determine outcome from response."
      echo "Response: $CREATE_USER_RESPONSE"
    fi
  elif [ "$HTTP_CODE" -eq 22 ]; then
    echo "Error: Invalid user data format for user '$(echo "$USER_JSON" | jq -r '.username')'."
    echo "$CREATE_USER_RESPONSE"
  elif [ "$HTTP_CODE" -eq 401 ]; then
    echo "Error: Unauthorized for user '$(echo "$USER_JSON" | jq -r '.username')'. Check your ACCESS_TOKEN."
  elif [ "$HTTP_CODE" -eq 403 ]; then
    echo "Error: Forbidden for user '$(echo "$USER_JSON" | jq -r '.username')'. Your token might not have the necessary permissions."
  elif [ "$HTTP_CODE" -eq 409 ]; then
    echo "User '$(echo "$USER_JSON" | jq -r '.username')' already exists."
  elif [ "$HTTP_CODE" -ge 400 ]; then
    echo "Error: Client error for user '$(echo "$USER_JSON" | jq -r '.username')'. HTTP Status Code: $HTTP_CODE"
    echo "Response: $CREATE_USER_RESPONSE"
  elif [ "$HTTP_CODE" -ge 500 ]; then
    echo "Error: Server error for user '$(echo "$USER_JSON" | jq -r '.username')'. HTTP Status Code: $HTTP_CODE"
    echo "Response: $CREATE_USER_RESPONSE"
  else
    echo "Error: Curl request failed for user '$(echo "$USER_JSON" | jq -r '.username')' with exit code: $HTTP_CODE"
    echo "Response: $CREATE_USER_RESPONSE"
  fi
done

echo "Script finished processing users."

exit 0
