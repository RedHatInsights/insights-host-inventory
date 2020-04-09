/*
 * Requires: https://github.com/RedHatInsights/insights-pipeline-lib
 */

@Library("github.com/RedHatInsights/insights-pipeline-lib@v3") _


if (env.CHANGE_ID) {
    execSmokeTest (
        ocDeployerBuilderPath: "inventory/insights-inventory",
        ocDeployerComponentPath: "inventory/insights-inventory",
        ocDeployerServiceSets: "advisor,engine,ingress,inventory,platform-mq",
        iqePlugins: ["iqe-advisor-plugin", "iqe-upload-plugin", "iqe-host-inventory-plugin"],
        pytestMarker: "smoke",
    )
}
