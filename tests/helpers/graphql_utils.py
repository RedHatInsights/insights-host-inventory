MOCK_XJOIN_HOST_RESPONSE = {
    "hosts": {
        "meta": {"total": 2},
        "data": [
            {
                "id": "6e7b6317-0a2d-4552-a2f2-b7da0aece49d",
                "account": "test",
                "display_name": "test01.rhel7.jharting.local",
                "ansible_host": "test01.rhel7.jharting.local",
                "created_on": "2019-02-10T08:07:03.354307Z",
                "modified_on": "2019-02-10T08:07:03.354312Z",
                "canonical_facts": {
                    "fqdn": "fqdn.test01.rhel7.jharting.local",
                    "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                    "insights_id": "a58c53e0-8000-4384-b902-c70b69faacc5",
                },
                "facts": None,
                "stale_timestamp": "2020-02-10T08:07:03.354307Z",
                "reporter": "puptoo",
            },
            {
                "id": "22cd8e39-13bb-4d02-8316-84b850dc5136",
                "account": "test",
                "display_name": "test02.rhel7.jharting.local",
                "ansible_host": "test02.rhel7.jharting.local",
                "created_on": "2019-01-10T08:07:03.354307Z",
                "modified_on": "2019-01-10T08:07:03.354312Z",
                "canonical_facts": {
                    "fqdn": "fqdn.test02.rhel7.jharting.local",
                    "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                    "insights_id": "17c52679-f0b9-4e9b-9bac-a3c7fae5070c",
                },
                "facts": {
                    "os": {"os.release": "Red Hat Enterprise Linux Server"},
                    "bios": {
                        "bios.vendor": "SeaBIOS",
                        "bios.release_date": "2014-04-01",
                        "bios.version": "1.11.0-2.el7",
                    },
                },
                "stale_timestamp": "2020-01-10T08:07:03.354307Z",
                "reporter": "puptoo",
            },
        ],
    }
}
