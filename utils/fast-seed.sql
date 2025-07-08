SET seed.num_rows = :num_rows;
SET seed.num_org_ids = :num_org_ids;
SET search_path = hbi;
DO $$
    DECLARE
        v_batch_start integer;
        v_batch_end integer;
        v_total_rows integer := current_setting('seed.num_rows')::integer;
        v_batch_size integer := 10000;
        v_start_time timestamp;
        v_batch_duration interval;
        v_rows_per_second numeric;
    BEGIN
        FOR v_batch_start IN 1..v_total_rows BY v_batch_size LOOP
                v_batch_end := LEAST(v_batch_start + v_batch_size - 1, v_total_rows);
                v_start_time := clock_timestamp();
                INSERT INTO hosts (
                    id,
                    account,
                    display_name,
                    created_on,
                    modified_on,
                    facts,
                    tags,
                    canonical_facts,
                    system_profile_facts,
                    ansible_host,
                    stale_timestamp,
                    reporter,
                    per_reporter_staleness,
                    org_id,
                    groups,
                    tags_alt,
                    last_check_in,
                    stale_warning_timestamp,
                    deletion_timestamp
                )
                SELECT
                    gen_random_uuid(),
                    NULL,
                    chr(97 + floor(random() * 26)::int) ||
                    chr(97 + floor(random() * 26)::int) ||
                    chr(97 + floor(random() * 26)::int) ||
                    chr(97 + floor(random() * 26)::int) ||
                    chr(97 + floor(random() * 26)::int) ||
                    chr(97 + floor(random() * 26)::int) ||
                    '.foo.redhat.com',
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    '{}'::jsonb,
                    '{"NS1": {"key3": ["val3"]}, "NS3": {"key3": ["val3"]}, "Sat": {"prod": []}, "SPECIAL": {"key": ["val"]}}'::jsonb,
                    -- Generate canonical_facts using md5 hash of row number + field name for unique UUIDs
                    -- Ensure at least one of insights_id, subscription_manager_id, or provider_id is present
                    (CASE 
                        WHEN random() > 0.66 THEN
                            jsonb_build_object('bios_uuid', md5(random()::text || 'bios' || gs)::uuid) ||
                            jsonb_build_object('insights_id', md5(random()::text || 'insights' || gs)::uuid) ||
                            CASE WHEN random() > 0.5 THEN jsonb_build_object('subscription_manager_id', md5(random()::text || 'sub' || gs)::uuid) ELSE '{}'::jsonb END ||
                            CASE WHEN random() > 0.5 THEN jsonb_build_object('provider_id', md5(random()::text || 'provider' || gs)::uuid) ||
                                                          jsonb_build_object('provider_type',
                                                                             (ARRAY['gcp', 'aws', 'azure', 'ibm'])[1 + floor(random() * 4)::int]) ELSE '{}'::jsonb END
                        WHEN random() > 0.33 THEN
                            jsonb_build_object('bios_uuid', md5(random()::text || 'bios' || gs)::uuid) ||
                            CASE WHEN random() > 0.5 THEN jsonb_build_object('insights_id', md5(random()::text || 'insights' || gs)::uuid) ELSE '{}'::jsonb END ||
                            jsonb_build_object('subscription_manager_id', md5(random()::text || 'sub' || gs)::uuid) ||
                            CASE WHEN random() > 0.5 THEN jsonb_build_object('provider_id', md5(random()::text || 'provider' || gs)::uuid) ||
                                                          jsonb_build_object('provider_type',
                                                                             (ARRAY['gcp', 'aws', 'azure', 'ibm'])[1 + floor(random() * 4)::int]) ELSE '{}'::jsonb END
                        ELSE
                            jsonb_build_object('bios_uuid', md5(random()::text || 'bios' || gs)::uuid) ||
                            CASE WHEN random() > 0.5 THEN jsonb_build_object('insights_id', md5(random()::text || 'insights' || gs)::uuid) ELSE '{}'::jsonb END ||
                            CASE WHEN random() > 0.5 THEN jsonb_build_object('subscription_manager_id', md5(random()::text || 'sub' || gs)::uuid) ELSE '{}'::jsonb END ||
                            jsonb_build_object('provider_id', md5(random()::text || 'provider' || gs)::uuid) ||
                            jsonb_build_object('provider_type',
                                               (ARRAY['gcp', 'aws', 'azure', 'ibm'])[1 + floor(random() * 4)::int])
                    END),
                    '{"arch": "x86-64", "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378", "cpu_flags": ["flag1", "flag2"], "cpu_model": "Intel(R) Xeon(R) CPU E5-2690 0 @ 2.90GHz", "yum_repos": [{"name": "repo1", "enabled": true, "base_url": "http://rpms.redhat.com", "gpgcheck": true}], "os_release": "Red Hat EL 7.0.1", "bios_vendor": "Turd Ferguson", "bios_version": "1.0.0uhoh", "disk_devices": [{"type": "ext3", "label": "home drive", "device": "/dev/sdb1", "options": {"ro": true, "uid": "0"}, "mount_point": "/home"}], "captured_date": "2020-02-13T12:16:00Z", "rhc_client_id": "044e36dc-4e2b-4e69-8948-9c65a7bf4976", "is_marketplace": false, "kernel_modules": ["i915", "e1000e"], "last_boot_time": "2020-02-13T12:08:55Z", "number_of_cpus": 1, "cores_per_socket": 4, "enabled_services": ["ndb", "krb5"], "operating_system": {"name": "RHEL", "major": 8, "minor": 1}, "rhc_config_state": "044e36dc-4e2b-4e69-8948-9c65a7bf4976", "bios_release_date": "10/31/2013", "number_of_sockets": 2, "os_kernel_version": "3.10.0", "running_processes": ["vim", "gcc", "python"], "satellite_managed": false, "installed_products": [{"id": "123", "name": "eap", "status": "UP"}, {"id": "321", "name": "jbws", "status": "DOWN"}], "installed_services": ["ndb", "krb5"], "network_interfaces": [{"mtu": 1500, "name": "eth0", "type": "loopback", "state": "UP", "mac_address": "aa:bb:cc:dd:ee:ff", "ipv4_addresses": ["10.10.10.1"], "ipv6_addresses": ["2001:0db8:85a3:0000:0000:8a2e:0370:7334"]}], "infrastructure_type": "jingleheimer junction cpu", "selinux_config_file": "enforcing", "subscription_status": "valid", "system_memory_bytes": 1024, "insights_egg_version": "120.0.1", "selinux_current_mode": "enforcing", "system_update_method": "yum", "infrastructure_vendor": "dell", "katello_agent_running": false, "insights_client_version": "12.0.12", "subscription_auto_attach": "yes"}'::jsonb,
                    NULL,
                    CURRENT_TIMESTAMP + INTERVAL '24 hours',
                    'puptoo',
                    jsonb_build_object('puptoo', jsonb_build_object(
                            'last_check_in', to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'),
                            'stale_timestamp', to_char(CURRENT_TIMESTAMP + INTERVAL '24 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'),
                            'check_in_succeeded', true
                                                 )),
                    LPAD(((100000 + (gs % current_setting('seed.num_org_ids')::integer)))::text, 6, '0'),
                    '[]'::jsonb,
                    '[{"key": "key", "value": "val", "namespace": "SPECIAL"}, {"key": "key3", "value": "val3", "namespace": "NS3"}, {"key": "key3", "value": "val3", "namespace": "NS1"}, {"key": "prod", "value": null, "namespace": "Sat"}]'::jsonb,
                    CURRENT_TIMESTAMP,
                    NULL,
                    NULL
                FROM generate_series(v_batch_start, v_batch_end) gs;


                v_batch_duration := clock_timestamp() - v_start_time;
                v_rows_per_second := (v_batch_end - v_batch_start + 1) / EXTRACT(EPOCH FROM v_batch_duration);

                IF v_batch_end % 20000 = 0 THEN
                    RAISE NOTICE 'Inserted % rows (% rows/sec for this batch)',
                        v_batch_end, ROUND(v_rows_per_second);
                END IF;
            END LOOP;
    END $$;
ANALYZE hosts;