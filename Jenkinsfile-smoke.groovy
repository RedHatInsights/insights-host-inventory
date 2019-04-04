/*
 * Requires: https://github.com/RedHatInsights/insights-pipeline-lib
 */

@Library("github.com/RedHatInsights/insights-pipeline-lib") _


if (env.CHANGE_ID) {
    runSmokeTest (
        ocDeployerBuilderPath: "platform/insights-inventory",
        ocDeployerComponentPath: "platform/insights-inventory",
        ocDeployerServiceSets: "advisor,platform,platform-mq",
        iqePlugins: ["iqe-advisor-plugin"],
        pytestMarker: "advisor_smoke",
    )
}
