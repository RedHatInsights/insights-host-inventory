/*
 * Requires: https://github.com/RedHatInsights/insights-pipeline-lib
 */

@Library("github.com/RedHatInsights/insights-pipeline-lib") _

podLabel = "${UUID.randomUUID().toString()}"

// Container names
pyContainer = "python3"
dbContainer = "postgres"
kafkaContainer = "kafka-1"
zookeeperContainer = "zookeeper-1"

// Directory where insights-host-inventory is checked out to
clientTargetDir = 'insights-host-inventory'
clientRepo = 'https://github.com/RedHatInsights/insights-host-inventory.git'

// Contact info for git commits
gitEmail = "rhinsightsbot@gmail.com"
gitName = "InsightsDroid"

// Code coverage failure threshold
codecovThreshold = 80


node {
    cancelPriorBuilds()
    runIfMasterOrPullReq {
        runStages()
    }
}


def updateClientRepo() {
    dir(clientTargetDir) {
        sh "git add --all ."
        def changes = sh(returnStdout: true, script: "git diff --cached --stat | wc -l").trim().toInteger()
        if (changes > 0) {
            sh "git commit -m \"Update client (Jenkins auto-update)\""
            sh "git push origin HEAD:master"
        }
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
            name: pyContainer,
            image: 'python:3.6.5',
            ttyEnabled: true,
            command: 'cat',
            resourceRequestCpu: '300m',
            resourceLimitCpu: '1000m',
            resourceRequestMemory: '512Mi',
            resourceLimitMemory: '1Gi'
        ),
        containerTemplate(
            name: dbContainer,
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
            sh "git config --global user.email \"${gitEmail}\""
            sh "git config --global user.name \"${gitName}\""

            // cache creds from the checkout so we can git push later...
            sh "git config --global credential.helper cache"
            sh "git config --global push.default simple"

            // check out source again to get it in this node's workspace
            scmVars = checkout scm

            container(pyContainer) {
                stage('Setting up environment') {
                    runPipenvInstall(scmVars: scmVars)
                }

                stage('Setting up database') {
                    sh "${pipelineVars.userPath}/pipenv run python manage.py db upgrade"
                }

                stage('Pre-commit checks') {
                    sh "${pipelineVars.userPath}/pipenv run pre-commit run --all"
                }

                stage('Unit Test') {
                    withStatusContext.unitTest {
                        sh "${pipelineVars.userPath}/pipenv run python -m pytest --cov=. --junitxml=junit.xml --cov-report html -s -v"
                    }

                    junit '*.xml'
                }

                stage('Code coverage') {
                    checkCoverage(threshold: codecovThreshold)
                }

            }

            archiveArtifacts 'htmlcov/*'
            archiveArtifacts '*.xml'

            if (currentBuild.currentResult == 'SUCCESS') {
                if (env.BRANCH_NAME == 'master') {
                    // Stages to run specifically if master branch was updated
                    stage('Update insights-host-inventory') {
                        updateClientRepo()
                    }
                }
            }
        }
    }
}
