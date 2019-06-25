                                       /*
 * Requires: https://github.com/RedHatInsights/insights-pipeline-lib
 */

@Library("github.com/RedHatInsights/insights-pipeline-lib") _

// Name for auto-generated openshift pod
podLabel = "host-inventory-test-${UUID.randomUUID().toString()}"

// Code coverage failure threshold
codecovThreshold = 80

venvDir = "venv"

node {
    cancelPriorBuilds()

    runIfMasterOrPullReq {
        runStages()
    }
}


def runStages() {

    // Fire up a pod on openshift with containers for the DB and the app
    podTemplate(label: podLabel, slaveConnectTimeout: 120, cloud: 'openshift', containers: [
        containerTemplate(
            name: 'jnlp',
            image: 'docker-registry.default.svc:5000/jenkins/jenkins-slave-base-centos7-python36',
            args: '${computer.jnlpmac} ${computer.name}',
            resourceRequestCpu: '200m',
            resourceLimitCpu: '500m',
            resourceRequestMemory: '256Mi',
            resourceLimitMemory: '650Mi'
        ),
        containerTemplate(
            name: 'postgres',
            image: 'postgres:9.6',
            ttyEnabled: true,
            envVars: [
                containerEnvVar(key: 'POSTGRES_USER', value: 'insights'),
                containerEnvVar(key: 'POSTGRES_PASSWORD', value: 'insights'),
                containerEnvVar(key: 'POSTGRES_DB', value: 'insights'),
                containerEnvVar(key: 'PGDATA', value: '/var/lib/postgresql/data/pgdata')
            ],
            volumes: [emptyDirVolume(mountPath: '/var/lib/postgresql/data/pgdata')],
            resourceRequestCpu: '200m',
            resourceLimitCpu: '200m',
            resourceRequestMemory: '100Mi',
            resourceLimitMemory: '100Mi'
        )
    ]) {
        node(podLabel) {
            // check out source again to get it in this node's workspace
            scmVars = checkout scm

            stage('Setting up virtual environment') {
                runPipenvInstall(scmVars: scmVars)
            }

            stage('Start app') {
                sh """
                    ${pipelineVars.userPath}/pipenv run python ./manage.py db upgrade
                    ${pipelineVars.userPath}/pipenv run python ./run.py > app.log 2>&1 &
                """
            }

            stage('Lint') {
                runPythonLintCheck()
            }

            stage('Unit tests') {
                withStatusContext.unitTest {
                    sh "${pipelineVars.userPath}/pipenv run pytest --cov=. --junitxml=junit.xml --cov-report html -s -v"
                    junit '*.xml'
                }
            }

            stage('Code coverage') {
                checkCoverage(threshold: codecovThreshold)
            }

            archiveArtifacts "app.log"
            archiveArtifacts "README.md"
            archiveArtifacts "junit.xml"
            archiveArtifacts "lint-results.txt"
            archiveArtifacts "htmlcov/*"
        }
    }
}
