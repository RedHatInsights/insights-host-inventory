/*
 * Requires: https://github.com/RedHatInsights/insights-pipeline-lib
 */

@Library("github.com/RedHatInsights/insights-pipeline-lib") _

podLabel = UUID.randomUUID().toString()

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
            image: 'registry.access.redhat.com/openshift3/jenkins-agent-nodejs-8-rhel7',
            args: '${computer.jnlpmac} ${computer.name}',
            resourceRequestCpu: '200m',
            resourceLimitCpu: '500m',
            resourceRequestMemory: '256Mi',
            resourceLimitMemory: '650Mi'
        ),
        containerTemplate(
            name: 'python3',
            image: 'python:3.6.5',
            ttyEnabled: true,
            command: 'cat',
            resourceRequestCpu: '300m',
            resourceLimitCpu: '1000m',
            resourceRequestMemory: '512Mi',
            resourceLimitMemory: '1Gi'
        ),
        containerTemplate(
            name: 'posgtres',
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
            sh "git config --global user.email \"rhinsightsbot@gmail.com\""
            sh "git config --global user.name \"InsightsDroid\""

            // cache creds from the checkout so we can git push later...
            sh "git config --global credential.helper cache"
            sh "git config --global push.default simple"

            // check out source again to get it in this node's workspace
            scmVars = checkout scm

            container('python3') {
                stage('Setting up environment') {
                    runPipenvInstall(scmVars: scmVars)
                }

                stage('Setting up database') {
                    withStatusContext.custom('database') {
                        sh "${pipelineVars.userPath}/pipenv run python manage.py db upgrade"
                    }
                }

                stage('Pre-commit checks') {
                    withStatusContext.custom('pre-commit') {
                        sh "${pipelineVars.userPath}/pipenv run pre-commit run --all"
                    }
                }

                stage('Unit Test') {
                    junitXml = 'junit.xml'
                    withStatusContext.unitTest {
                        sh "${pipelineVars.userPath}/pipenv run python -m pytest --cov=. --junitxml=${junitXml} --cov-report html -s -v"
                    }

                    junit junitXml
                    archiveArtifacts junitXml
                }

                stage('Code coverage') {
                    checkCoverage(threshold: 80)
                }

            }
        }
    }
}
