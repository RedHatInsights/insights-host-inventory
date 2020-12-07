# Error out if sonar scanner isn't installed and configured properly
if [[ -z "${SONAR_PATH}" ]]
then
    echo "Scanner jar required! Download it from here https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-4.5.0.2216.zip, and then set the env var with SONAR_PATH=/path/to/sonar-scanner/lib/sonar-scanner-cli-4.5.0.2216.jar"
    exit 1
fi

if [[ -z "${SONAR_HOST}" ]]
then
    HOST="https://sonarqube.corp.redhat.com/"
else
    HOST=${SONAR_HOST}
fi

if [ ! -e ./.sonar/sonar-scanner.properties ]
then
    sed "s|\$user|$(whoami)|g; s|\$host|$HOST|g" ./.sonar/sonar-scanner.properties.template > ./.sonar/sonar-scanner.properties
    echo "File .sonar/sonar-scanner.properties created."
    echo "Please replace the \$token\$ value in that file with your Sonar login token, and then run this script again."
    exit
fi

pytest --cov=. --cov-report=xml
java -jar $SONAR_PATH -Dproject.settings=.sonar/sonar-scanner.properties
