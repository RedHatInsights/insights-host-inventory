#!/bin/bash

SP_URL=https://raw.githubusercontent.com/RedHatInsights/inventory-schemas/master/schemas/system_profile/v1.yaml
SAVE_LOC=swagger/system_profile.spec.yaml

echo Downloading $SP_URL to $SAVE_LOC

curl $SP_URL -o $SAVE_LOC
