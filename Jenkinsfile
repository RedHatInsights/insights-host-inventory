/*
 * Requires: https://github.com/RedHatInsights/insights-pipeline-lib
 */

@Library("github.com/RedHatInsights/insights-pipeline-lib@v1.3") _

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
            image: 'python:3.8',
            ttyEnabled: true,
            command: 'cat',
            resourceRequestCpu: '300m',
            resourceLimitCpu: '1000m',
            resourceRequestMemory: '512Mi',
            resourceLimitMemory: '1Gi'
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
            container("python3") {
                stage('Setting up environment') {
                    withStatusContext.custom('setup') {
                        scmVars = checkout scm
                        runPipenvInstall(scmVars: scmVars)
                        sh "${pipelineVars.userPath}/pipenv run python manage.py db upgrade"
                    }
                }

                stage('Pre-commit checks') {
                    withStatusContext.custom('pre-commit') {
                        sh "${pipelineVars.userPath}/pipenv run pre-commit run --all-files"
                        sh "${pipelineVars.userPath}/pipenv run python utils/validate_dashboards.py"
                    }
                }

                stage('Unit Test') {
                    jUnitFile = 'junit.xml'

                    withStatusContext.unitTest {
                        sh "${pipelineVars.userPath}/pipenv run python -m pytest --cov=. --junitxml=${jUnitFile} --cov-report html -sv"
                    }

                    junit jUnitFile
                    archiveArtifacts jUnitFile
                    archiveArtifacts "htmlcov/*"
                }

                stage('Code coverage') {
                    checkCoverage(threshold: 80)
                }

            }
        }
    }
}
