/*
 * Requires: https://github.com/RedHatInsights/insights-pipeline-lib
 */

@Library("github.com/RedHatInsights/insights-pipeline-lib@v1.3") _


if (env.CHANGE_ID) {
    runSmokeTest (
        ocDeployerBuilderPath: "platform/insights-inventory",
        ocDeployerComponentPath: "platform/insights-inventory",
        ocDeployerServiceSets: "advisor,platform,platform-mq",
        iqePlugins: ["iqe-advisor-plugin", "iqe-upload-plugin", "iqe-host-inventory-plugin"],
        pytestMarker: "smoke",
    )
}
