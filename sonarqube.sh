#!/bin/bash

export SONAR_SCANNER_OS="linux"
if [[ "$OSTYPE" == "darwin"* ]]; then
    export SONAR_SCANNER_OS="macosx"
fi

COMMIT_SHORT=$(git rev-parse --short=7 HEAD)

sudo chown -R 1000:1000 .

docker run \
  -v "$(pwd)":/usr/src \
  -e SONAR_HOST_URL=https://sonarqube.corp.redhat.com/ \
  -e SONAR_SCANNER_HOME=/opt/sonar-scanner \
  -e SONAR_USER_HOME=/opt/sonar-scanner/.sonar \
  -e SONAR_SCANNER_OPTS="-Xmx512m -Dsonar.projectKey=console.redhat.com:insights-host-inventory -Dsonar.projectVersion=${COMMIT_SHORT} -Dsonar.sources=/usr/src" \
  -e SONAR_TOKEN=$SONARQUBE_TOKEN \
  images.paas.redhat.com/alm/sonar-scanner-alpine \
  sonar-scanner

mkdir -p $WORKSPACE/artifacts
cat << EOF > ${WORKSPACE}/artifacts/junit-dummy.xml
<testsuite tests="1">
    <testcase classname="dummy" name="dummytest"/>
</testsuite>
EOF
