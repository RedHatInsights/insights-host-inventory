--
-- PostgreSQL database dump
--

-- Dumped from database version 16.1 (Debian 16.1-1.pgdg120+1)
-- Dumped by pg_dump version 16.4 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: hbi; Type: SCHEMA; Schema: -; Owner: insights
--

CREATE SCHEMA IF NOT EXISTS hbi;


ALTER SCHEMA hbi OWNER TO insights;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: assignment_rules; Type: TABLE; Schema: hbi; Owner: insights
--

CREATE TABLE hbi.assignment_rules (
    id uuid NOT NULL,
    org_id character varying(36) NOT NULL,
    account character varying(10),
    name character varying(255) NOT NULL,
    description character varying(255),
    group_id uuid NOT NULL,
    filter jsonb DEFAULT '{}'::jsonb NOT NULL,
    enabled boolean,
    created_on timestamp with time zone NOT NULL,
    modified_on timestamp with time zone NOT NULL
);


ALTER TABLE hbi.assignment_rules OWNER TO insights;

--
-- Name: groups; Type: TABLE; Schema: hbi; Owner: insights
--

CREATE TABLE hbi.groups (
    id uuid NOT NULL,
    org_id character varying(36) NOT NULL,
    account character varying(10),
    name character varying(255) NOT NULL,
    created_on timestamp with time zone NOT NULL,
    modified_on timestamp with time zone NOT NULL
);


ALTER TABLE hbi.groups OWNER TO insights;

--
-- Name: hosts; Type: TABLE; Schema: hbi; Owner: insights
--

CREATE TABLE hbi.hosts (
    id uuid NOT NULL,
    account character varying(10),
    display_name character varying(200),
    created_on timestamp with time zone NOT NULL,
    modified_on timestamp with time zone NOT NULL,
    facts jsonb,
    tags jsonb,
    canonical_facts jsonb NOT NULL,
    system_profile_facts jsonb,
    ansible_host character varying(255),
    stale_timestamp timestamp with time zone NOT NULL,
    reporter character varying(255) NOT NULL,
    per_reporter_staleness jsonb DEFAULT '{}'::jsonb NOT NULL,
    org_id character varying(36) NOT NULL,
    groups jsonb NOT NULL
);

ALTER TABLE ONLY hbi.hosts REPLICA IDENTITY FULL;


ALTER TABLE hbi.hosts OWNER TO insights;

--
-- Name: hosts_groups; Type: TABLE; Schema: hbi; Owner: insights
--

CREATE TABLE hbi.hosts_groups (
    group_id uuid NOT NULL,
    host_id uuid NOT NULL
);


ALTER TABLE hbi.hosts_groups OWNER TO insights;

--
-- Name: staleness; Type: TABLE; Schema: hbi; Owner: insights
--

CREATE TABLE hbi.staleness (
    id uuid NOT NULL,
    org_id character varying(36) NOT NULL,
    conventional_time_to_stale integer NOT NULL,
    conventional_time_to_stale_warning integer NOT NULL,
    conventional_time_to_delete integer NOT NULL,
    immutable_time_to_stale integer NOT NULL,
    immutable_time_to_stale_warning integer NOT NULL,
    immutable_time_to_delete integer NOT NULL,
    created_on timestamp with time zone NOT NULL,
    modified_on timestamp with time zone NOT NULL
);


ALTER TABLE hbi.staleness OWNER TO insights;

--
-- Name: assignment_rules assignment_rules_org_id_name_key; Type: CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.assignment_rules
    ADD CONSTRAINT assignment_rules_org_id_name_key UNIQUE (org_id, name);


--
-- Name: assignment_rules assignment_rules_pkey; Type: CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.assignment_rules
    ADD CONSTRAINT assignment_rules_pkey PRIMARY KEY (id, group_id);


--
-- Name: assignment_rules assignment_rules_unique_group_id; Type: CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.assignment_rules
    ADD CONSTRAINT assignment_rules_unique_group_id UNIQUE (group_id);


--
-- Name: groups groups_pkey; Type: CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.groups
    ADD CONSTRAINT groups_pkey PRIMARY KEY (id);

ALTER TABLE ONLY hbi.groups REPLICA IDENTITY USING INDEX groups_pkey;


--
-- Name: hosts_groups hosts_groups_pkey; Type: CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.hosts_groups
    ADD CONSTRAINT hosts_groups_pkey PRIMARY KEY (group_id, host_id);

ALTER TABLE ONLY hbi.hosts_groups REPLICA IDENTITY USING INDEX hosts_groups_pkey;


--
-- Name: hosts_groups hosts_groups_unique_host_id; Type: CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.hosts_groups
    ADD CONSTRAINT hosts_groups_unique_host_id UNIQUE (host_id);


--
-- Name: hosts hosts_pkey; Type: CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.hosts
    ADD CONSTRAINT hosts_pkey PRIMARY KEY (id);


--
-- Name: staleness staleness_org_id_key; Type: CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.staleness
    ADD CONSTRAINT staleness_org_id_key UNIQUE (org_id);


--
-- Name: staleness staleness_pkey; Type: CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.staleness
    ADD CONSTRAINT staleness_pkey PRIMARY KEY (id);

ALTER TABLE ONLY hbi.staleness REPLICA IDENTITY USING INDEX staleness_pkey;


--
-- Name: alt_where; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX alt_where ON hbi.hosts USING btree (org_id, ((system_profile_facts ->> 'host_type'::text)), modified_on, ((canonical_facts -> 'insights_id'::text)));


--
-- Name: hosts_modified_on_id; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX hosts_modified_on_id ON hbi.hosts USING btree (modified_on DESC, id DESC);


--
-- Name: idx_groups_org_id_name_nocase; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE UNIQUE INDEX idx_groups_org_id_name_nocase ON hbi.groups USING btree (org_id, lower((name)::text));


--
-- Name: idx_host_type; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idx_host_type ON hbi.hosts USING btree (((system_profile_facts ->> 'host_type'::text)));


--
-- Name: idx_host_type_modified_on_org_id; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idx_host_type_modified_on_org_id ON hbi.hosts USING btree (org_id, modified_on, ((system_profile_facts ->> 'host_type'::text)));


--
-- Name: idx_operating_system_multi; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idx_operating_system_multi ON hbi.hosts USING btree ((((system_profile_facts -> 'operating_system'::text) ->> 'name'::text)), ((((system_profile_facts -> 'operating_system'::text) ->> 'major'::text))::integer), ((((system_profile_facts -> 'operating_system'::text) ->> 'minor'::text))::integer), ((system_profile_facts ->> 'host_type'::text)), modified_on, org_id) WHERE ((system_profile_facts -> 'operating_system'::text) IS NOT NULL);


--
-- Name: idxaccstaleorgid; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idxaccstaleorgid ON hbi.staleness USING btree (org_id);


--
-- Name: idxansible; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idxansible ON hbi.hosts USING btree (((system_profile_facts ->> 'ansible'::text)));


--
-- Name: idxassrulesorgid; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idxassrulesorgid ON hbi.assignment_rules USING btree (org_id);


--
-- Name: idxbootc_status; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idxbootc_status ON hbi.hosts USING btree (org_id) WHERE ((((system_profile_facts -> 'bootc_status'::text) -> 'booted'::text) ->> 'image_digest'::text) IS NOT NULL);


--
-- Name: idxgincanonicalfacts; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idxgincanonicalfacts ON hbi.hosts USING gin (canonical_facts jsonb_path_ops);


--
-- Name: idxgrouporgid; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idxgrouporgid ON hbi.groups USING btree (org_id);


--
-- Name: idxgroupshosts; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE UNIQUE INDEX idxgroupshosts ON hbi.hosts_groups USING btree (group_id, host_id);


--
-- Name: idxhostsgroups; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE UNIQUE INDEX idxhostsgroups ON hbi.hosts_groups USING btree (host_id, group_id);


--
-- Name: idxinsightsid; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idxinsightsid ON hbi.hosts USING btree (((canonical_facts ->> 'insights_id'::text)));


--
-- Name: idxmssql; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idxmssql ON hbi.hosts USING btree (((system_profile_facts ->> 'mssql'::text)));


--
-- Name: idxorgid; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idxorgid ON hbi.hosts USING btree (org_id);


--
-- Name: idxsap_system; Type: INDEX; Schema: hbi; Owner: insights
--

CREATE INDEX idxsap_system ON hbi.hosts USING btree ((((system_profile_facts ->> 'sap_system'::text))::boolean));


--
-- Name: assignment_rules assignment_rules_group_id_fkey; Type: FK CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.assignment_rules
    ADD CONSTRAINT assignment_rules_group_id_fkey FOREIGN KEY (group_id) REFERENCES hbi.groups(id);


--
-- Name: hosts_groups hosts_groups_group_id_fkey; Type: FK CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.hosts_groups
    ADD CONSTRAINT hosts_groups_group_id_fkey FOREIGN KEY (group_id) REFERENCES hbi.groups(id);


--
-- Name: hosts_groups hosts_groups_host_id_fkey; Type: FK CONSTRAINT; Schema: hbi; Owner: insights
--

ALTER TABLE ONLY hbi.hosts_groups
    ADD CONSTRAINT hosts_groups_host_id_fkey FOREIGN KEY (host_id) REFERENCES hbi.hosts(id);
