/*
 * Requires: https://github.com/RedHatInsights/insights-pipeline-lib
 */

@Library("github.com/RedHatInsights/insights-pipeline-lib@v3") _


if (env.CHANGE_ID) {
    execSmokeTest (
        ocDeployerBuilderPath: "platform/insights-inventory",
        ocDeployerComponentPath: "platform/insights-inventory",
        ocDeployerServiceSets: "advisor,ingress,inventory,platform-mq",
        iqePlugins: ["iqe-advisor-plugin", "iqe-upload-plugin", "iqe-host-inventory-plugin"],
        pytestMarker: "smoke",
    )
}
