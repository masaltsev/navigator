--
-- PostgreSQL database dump
--

\restrict EDqqaHmb1ccxxxyna1KkQXFvDnoXJL5EJTjIqIcS9JtqhSwEKmnqe5estFBEyhm

-- Dumped from database version 18.2 (Homebrew)
-- Dumped by pg_dump version 18.2 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: postgis; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;


--
-- Name: EXTENSION postgis; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION postgis IS 'PostGIS geometry and geography spatial types and functions';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: articles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.articles (
    id uuid NOT NULL,
    title character varying(255) NOT NULL,
    slug character varying(255) NOT NULL,
    content_url text,
    content text,
    excerpt text,
    featured_image_url character varying(255),
    related_thematic_category_id bigint,
    related_service_id bigint,
    organization_id uuid,
    status character varying(255) DEFAULT 'draft'::character varying NOT NULL,
    published_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    CONSTRAINT articles_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'published'::character varying, 'archived'::character varying])::text[])))
);


--
-- Name: cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cache (
    key character varying(255) NOT NULL,
    value text NOT NULL,
    expiration integer NOT NULL
);


--
-- Name: cache_locks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cache_locks (
    key character varying(255) NOT NULL,
    owner character varying(255) NOT NULL,
    expiration integer NOT NULL
);


--
-- Name: coverage_levels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.coverage_levels (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    weight_index integer NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: coverage_levels_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.coverage_levels_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: coverage_levels_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.coverage_levels_id_seq OWNED BY public.coverage_levels.id;


--
-- Name: event_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_categories (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(255) NOT NULL,
    code character varying(255),
    icon_url character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: event_categories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.event_categories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: event_categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.event_categories_id_seq OWNED BY public.event_categories.id;


--
-- Name: event_event_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_event_categories (
    event_id uuid NOT NULL,
    event_category_id bigint NOT NULL
);


--
-- Name: event_instances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_instances (
    id uuid NOT NULL,
    event_id uuid NOT NULL,
    start_datetime timestamp(0) with time zone NOT NULL,
    end_datetime timestamp(0) with time zone NOT NULL,
    status character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    CONSTRAINT event_instances_status_check CHECK (((status)::text = ANY ((ARRAY['scheduled'::character varying, 'cancelled'::character varying, 'rescheduled'::character varying, 'finished'::character varying])::text[])))
);


--
-- Name: event_venues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_venues (
    event_id uuid NOT NULL,
    venue_id uuid NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events (
    id uuid NOT NULL,
    organizer_id uuid NOT NULL,
    organization_id uuid,
    title character varying(255) NOT NULL,
    description text,
    attendance_mode character varying(255) NOT NULL,
    online_url character varying(255),
    rrule_string character varying(255),
    target_audience jsonb,
    ai_confidence_score numeric(8,4),
    ai_explanation text,
    ai_source_trace jsonb,
    status character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    source_reference character varying(255),
    event_page_url character varying(255),
    CONSTRAINT events_attendance_mode_check CHECK (((attendance_mode)::text = ANY ((ARRAY['offline'::character varying, 'online'::character varying, 'mixed'::character varying])::text[])))
);


--
-- Name: failed_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.failed_jobs (
    id bigint NOT NULL,
    uuid character varying(255) NOT NULL,
    connection text NOT NULL,
    queue text NOT NULL,
    payload text NOT NULL,
    exception text NOT NULL,
    failed_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: failed_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.failed_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: failed_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.failed_jobs_id_seq OWNED BY public.failed_jobs.id;


--
-- Name: individuals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.individuals (
    id uuid NOT NULL,
    full_name character varying(255) NOT NULL,
    role character varying(255),
    contact_email character varying(255),
    contact_phone character varying(255),
    consent_given boolean DEFAULT false NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: initiative_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.initiative_groups (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    community_focus character varying(255),
    established_date date,
    works_with_elderly boolean DEFAULT false NOT NULL,
    ai_confidence_score numeric(8,4),
    ai_explanation text,
    ai_source_trace jsonb,
    target_audience jsonb,
    status character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: job_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_batches (
    id character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    total_jobs integer NOT NULL,
    pending_jobs integer NOT NULL,
    failed_jobs integer NOT NULL,
    failed_job_ids text NOT NULL,
    options text,
    cancelled_at integer,
    created_at integer NOT NULL,
    finished_at integer
);


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    id bigint NOT NULL,
    queue character varying(255) NOT NULL,
    payload text NOT NULL,
    attempts smallint NOT NULL,
    reserved_at integer,
    available_at integer NOT NULL,
    created_at integer NOT NULL
);


--
-- Name: jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.jobs_id_seq OWNED BY public.jobs.id;


--
-- Name: migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.migrations (
    id integer NOT NULL,
    migration character varying(255) NOT NULL,
    batch integer NOT NULL
);


--
-- Name: migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.migrations_id_seq OWNED BY public.migrations.id;


--
-- Name: organization_organization_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization_organization_types (
    organization_id uuid NOT NULL,
    organization_type_id bigint NOT NULL
);


--
-- Name: organization_services; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization_services (
    organization_id uuid NOT NULL,
    service_id bigint NOT NULL
);


--
-- Name: organization_specialist_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization_specialist_profiles (
    organization_id uuid NOT NULL,
    specialist_profile_id bigint NOT NULL
);


--
-- Name: organization_thematic_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization_thematic_categories (
    organization_id uuid NOT NULL,
    thematic_category_id bigint NOT NULL
);


--
-- Name: organization_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization_types (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    code character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    description text,
    keywords json
);


--
-- Name: organization_types_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.organization_types_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: organization_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.organization_types_id_seq OWNED BY public.organization_types.id;


--
-- Name: organization_venues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization_venues (
    organization_id uuid NOT NULL,
    venue_id uuid NOT NULL,
    is_headquarters boolean DEFAULT false NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    id uuid NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    inn character varying(255),
    ogrn character varying(255),
    site_urls jsonb,
    ownership_type_id bigint,
    coverage_level_id bigint,
    works_with_elderly boolean DEFAULT false NOT NULL,
    ai_confidence_score numeric(8,4),
    ai_explanation text,
    ai_source_trace jsonb,
    target_audience jsonb,
    vk_group_id bigint,
    ok_group_id bigint,
    status character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    source_reference character varying(255),
    short_title character varying(100)
);


--
-- Name: organizers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizers (
    id uuid NOT NULL,
    organizable_type character varying(255) NOT NULL,
    organizable_id uuid NOT NULL,
    contact_phones jsonb,
    contact_emails jsonb,
    status character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: ownership_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ownership_types (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    code character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    description text,
    keywords json
);


--
-- Name: ownership_types_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ownership_types_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ownership_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ownership_types_id_seq OWNED BY public.ownership_types.id;


--
-- Name: parse_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parse_profiles (
    id uuid NOT NULL,
    source_id uuid NOT NULL,
    entity_type character varying(255) NOT NULL,
    crawl_strategy character varying(255) NOT NULL,
    config jsonb NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_reset_tokens (
    email character varying(255) NOT NULL,
    token character varying(255) NOT NULL,
    created_at timestamp(0) without time zone
);


--
-- Name: role_user; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_user (
    user_id bigint NOT NULL,
    role_id bigint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: roles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.roles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.roles_id_seq OWNED BY public.roles.id;


--
-- Name: services; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.services (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    code character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    parent_id bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    description text,
    keywords json
);


--
-- Name: services_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.services_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: services_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.services_id_seq OWNED BY public.services.id;


--
-- Name: sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sessions (
    id character varying(255) NOT NULL,
    user_id bigint,
    ip_address character varying(45),
    user_agent text,
    payload text NOT NULL,
    last_activity integer NOT NULL
);


--
-- Name: sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sources (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    kind character varying(255) NOT NULL,
    region_iso character varying(255),
    fias_region_id uuid,
    base_url text NOT NULL,
    entry_points jsonb DEFAULT '[]'::jsonb NOT NULL,
    parse_profile_id uuid,
    crawl_period_days integer DEFAULT 7 NOT NULL,
    last_crawled_at timestamp(0) with time zone,
    last_status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    priority integer DEFAULT 50 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    organizer_id uuid
);


--
-- Name: specialist_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.specialist_profiles (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    code character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    description text,
    keywords json
);


--
-- Name: specialist_profiles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.specialist_profiles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: specialist_profiles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.specialist_profiles_id_seq OWNED BY public.specialist_profiles.id;


--
-- Name: suggested_taxonomy_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suggested_taxonomy_items (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    source_reference character varying(255),
    dictionary_type character varying(255) NOT NULL,
    suggested_name character varying(255) NOT NULL,
    ai_reasoning text,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: target_audience; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.target_audience (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    code character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: target_audience_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.target_audience_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: target_audience_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.target_audience_id_seq OWNED BY public.target_audience.id;


--
-- Name: thematic_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.thematic_categories (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    code character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    parent_id bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    description text,
    keywords json
);


--
-- Name: thematic_categories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.thematic_categories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: thematic_categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.thematic_categories_id_seq OWNED BY public.thematic_categories.id;


--
-- Name: user_organizer; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_organizer (
    user_id bigint NOT NULL,
    organizer_id uuid NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    email_verified_at timestamp(0) without time zone,
    password character varying(255) NOT NULL,
    remember_token character varying(100),
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: venues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.venues (
    id uuid NOT NULL,
    address_raw character varying(255) NOT NULL,
    fias_id character varying(255),
    kladr_id character varying(255),
    region_iso character varying(255),
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    coordinates public.geometry(Point,4326),
    fias_level character varying(10),
    city_fias_id character varying(36),
    region_code character varying(255)
);


--
-- Name: coverage_levels id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coverage_levels ALTER COLUMN id SET DEFAULT nextval('public.coverage_levels_id_seq'::regclass);


--
-- Name: event_categories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_categories ALTER COLUMN id SET DEFAULT nextval('public.event_categories_id_seq'::regclass);


--
-- Name: failed_jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_jobs ALTER COLUMN id SET DEFAULT nextval('public.failed_jobs_id_seq'::regclass);


--
-- Name: jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs ALTER COLUMN id SET DEFAULT nextval('public.jobs_id_seq'::regclass);


--
-- Name: migrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.migrations ALTER COLUMN id SET DEFAULT nextval('public.migrations_id_seq'::regclass);


--
-- Name: organization_types id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_types ALTER COLUMN id SET DEFAULT nextval('public.organization_types_id_seq'::regclass);


--
-- Name: ownership_types id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ownership_types ALTER COLUMN id SET DEFAULT nextval('public.ownership_types_id_seq'::regclass);


--
-- Name: roles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles ALTER COLUMN id SET DEFAULT nextval('public.roles_id_seq'::regclass);


--
-- Name: services id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services ALTER COLUMN id SET DEFAULT nextval('public.services_id_seq'::regclass);


--
-- Name: specialist_profiles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.specialist_profiles ALTER COLUMN id SET DEFAULT nextval('public.specialist_profiles_id_seq'::regclass);


--
-- Name: target_audience id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.target_audience ALTER COLUMN id SET DEFAULT nextval('public.target_audience_id_seq'::regclass);


--
-- Name: thematic_categories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thematic_categories ALTER COLUMN id SET DEFAULT nextval('public.thematic_categories_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: articles articles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_pkey PRIMARY KEY (id);


--
-- Name: articles articles_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_slug_unique UNIQUE (slug);


--
-- Name: cache_locks cache_locks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cache_locks
    ADD CONSTRAINT cache_locks_pkey PRIMARY KEY (key);


--
-- Name: cache cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cache
    ADD CONSTRAINT cache_pkey PRIMARY KEY (key);


--
-- Name: coverage_levels coverage_levels_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coverage_levels
    ADD CONSTRAINT coverage_levels_pkey PRIMARY KEY (id);


--
-- Name: event_categories event_categories_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_categories
    ADD CONSTRAINT event_categories_code_unique UNIQUE (code);


--
-- Name: event_categories event_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_categories
    ADD CONSTRAINT event_categories_pkey PRIMARY KEY (id);


--
-- Name: event_categories event_categories_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_categories
    ADD CONSTRAINT event_categories_slug_unique UNIQUE (slug);


--
-- Name: event_event_categories event_event_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_event_categories
    ADD CONSTRAINT event_event_categories_pkey PRIMARY KEY (event_id, event_category_id);


--
-- Name: event_instances event_instances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_instances
    ADD CONSTRAINT event_instances_pkey PRIMARY KEY (id);


--
-- Name: event_venues event_venues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_venues
    ADD CONSTRAINT event_venues_pkey PRIMARY KEY (event_id, venue_id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: failed_jobs failed_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_jobs
    ADD CONSTRAINT failed_jobs_pkey PRIMARY KEY (id);


--
-- Name: failed_jobs failed_jobs_uuid_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_jobs
    ADD CONSTRAINT failed_jobs_uuid_unique UNIQUE (uuid);


--
-- Name: individuals individuals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.individuals
    ADD CONSTRAINT individuals_pkey PRIMARY KEY (id);


--
-- Name: initiative_groups initiative_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiative_groups
    ADD CONSTRAINT initiative_groups_pkey PRIMARY KEY (id);


--
-- Name: job_batches job_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_batches
    ADD CONSTRAINT job_batches_pkey PRIMARY KEY (id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: migrations migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.migrations
    ADD CONSTRAINT migrations_pkey PRIMARY KEY (id);


--
-- Name: organization_organization_types organization_organization_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_organization_types
    ADD CONSTRAINT organization_organization_types_pkey PRIMARY KEY (organization_id, organization_type_id);


--
-- Name: organization_services organization_services_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_services
    ADD CONSTRAINT organization_services_pkey PRIMARY KEY (organization_id, service_id);


--
-- Name: organization_specialist_profiles organization_specialist_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_specialist_profiles
    ADD CONSTRAINT organization_specialist_profiles_pkey PRIMARY KEY (organization_id, specialist_profile_id);


--
-- Name: organization_thematic_categories organization_thematic_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_thematic_categories
    ADD CONSTRAINT organization_thematic_categories_pkey PRIMARY KEY (organization_id, thematic_category_id);


--
-- Name: organization_types organization_types_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_types
    ADD CONSTRAINT organization_types_code_unique UNIQUE (code);


--
-- Name: organization_types organization_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_types
    ADD CONSTRAINT organization_types_pkey PRIMARY KEY (id);


--
-- Name: organization_venues organization_venues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_venues
    ADD CONSTRAINT organization_venues_pkey PRIMARY KEY (organization_id, venue_id);


--
-- Name: organizations organizations_inn_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_inn_unique UNIQUE (inn);


--
-- Name: organizations organizations_ogrn_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_ogrn_unique UNIQUE (ogrn);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--
-- Name: organizers organizers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizers
    ADD CONSTRAINT organizers_pkey PRIMARY KEY (id);


--
-- Name: ownership_types ownership_types_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ownership_types
    ADD CONSTRAINT ownership_types_code_unique UNIQUE (code);


--
-- Name: ownership_types ownership_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ownership_types
    ADD CONSTRAINT ownership_types_pkey PRIMARY KEY (id);


--
-- Name: parse_profiles parse_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parse_profiles
    ADD CONSTRAINT parse_profiles_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (email);


--
-- Name: role_user role_user_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_user
    ADD CONSTRAINT role_user_pkey PRIMARY KEY (user_id, role_id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: roles roles_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_slug_unique UNIQUE (slug);


--
-- Name: services services_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services
    ADD CONSTRAINT services_code_unique UNIQUE (code);


--
-- Name: services services_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services
    ADD CONSTRAINT services_pkey PRIMARY KEY (id);


--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


--
-- Name: sources sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (id);


--
-- Name: specialist_profiles specialist_profiles_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.specialist_profiles
    ADD CONSTRAINT specialist_profiles_code_unique UNIQUE (code);


--
-- Name: specialist_profiles specialist_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.specialist_profiles
    ADD CONSTRAINT specialist_profiles_pkey PRIMARY KEY (id);


--
-- Name: suggested_taxonomy_items suggested_taxonomy_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggested_taxonomy_items
    ADD CONSTRAINT suggested_taxonomy_items_pkey PRIMARY KEY (id);


--
-- Name: target_audience target_audience_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.target_audience
    ADD CONSTRAINT target_audience_code_unique UNIQUE (code);


--
-- Name: target_audience target_audience_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.target_audience
    ADD CONSTRAINT target_audience_pkey PRIMARY KEY (id);


--
-- Name: thematic_categories thematic_categories_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thematic_categories
    ADD CONSTRAINT thematic_categories_code_unique UNIQUE (code);


--
-- Name: thematic_categories thematic_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thematic_categories
    ADD CONSTRAINT thematic_categories_pkey PRIMARY KEY (id);


--
-- Name: user_organizer user_organizer_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizer
    ADD CONSTRAINT user_organizer_pkey PRIMARY KEY (user_id, organizer_id);


--
-- Name: users users_email_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_unique UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: venues venues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.venues
    ADD CONSTRAINT venues_pkey PRIMARY KEY (id);


--
-- Name: articles_organization_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX articles_organization_id_index ON public.articles USING btree (organization_id);


--
-- Name: articles_published_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX articles_published_at_index ON public.articles USING btree (published_at);


--
-- Name: articles_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX articles_status_index ON public.articles USING btree (status);


--
-- Name: cache_expiration_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX cache_expiration_index ON public.cache USING btree (expiration);


--
-- Name: cache_locks_expiration_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX cache_locks_expiration_index ON public.cache_locks USING btree (expiration);


--
-- Name: coverage_levels_name_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX coverage_levels_name_index ON public.coverage_levels USING btree (name);


--
-- Name: coverage_levels_weight_index_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX coverage_levels_weight_index_index ON public.coverage_levels USING btree (weight_index);


--
-- Name: event_categories_name_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX event_categories_name_index ON public.event_categories USING btree (name);


--
-- Name: event_instances_end_datetime_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX event_instances_end_datetime_index ON public.event_instances USING btree (end_datetime);


--
-- Name: event_instances_event_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX event_instances_event_id_index ON public.event_instances USING btree (event_id);


--
-- Name: event_instances_start_datetime_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX event_instances_start_datetime_index ON public.event_instances USING btree (start_datetime);


--
-- Name: event_instances_start_datetime_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX event_instances_start_datetime_status_index ON public.event_instances USING btree (start_datetime, status);


--
-- Name: events_organization_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_organization_id_index ON public.events USING btree (organization_id);


--
-- Name: events_organizer_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_organizer_id_index ON public.events USING btree (organizer_id);


--
-- Name: events_source_reference_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_source_reference_index ON public.events USING btree (source_reference);


--
-- Name: events_status_attendance_mode_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_status_attendance_mode_index ON public.events USING btree (status, attendance_mode);


--
-- Name: events_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_status_index ON public.events USING btree (status);


--
-- Name: initiative_groups_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX initiative_groups_status_index ON public.initiative_groups USING btree (status);


--
-- Name: initiative_groups_works_with_elderly_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX initiative_groups_works_with_elderly_index ON public.initiative_groups USING btree (works_with_elderly);


--
-- Name: jobs_queue_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX jobs_queue_index ON public.jobs USING btree (queue);


--
-- Name: organization_types_name_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX organization_types_name_index ON public.organization_types USING btree (name);


--
-- Name: organizations_ok_group_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX organizations_ok_group_id_index ON public.organizations USING btree (ok_group_id);


--
-- Name: organizations_source_reference_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX organizations_source_reference_index ON public.organizations USING btree (source_reference);


--
-- Name: organizations_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX organizations_status_index ON public.organizations USING btree (status);


--
-- Name: organizations_vk_group_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX organizations_vk_group_id_index ON public.organizations USING btree (vk_group_id);


--
-- Name: organizations_works_with_elderly_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX organizations_works_with_elderly_index ON public.organizations USING btree (works_with_elderly);


--
-- Name: organizers_organizable_type_organizable_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX organizers_organizable_type_organizable_id_index ON public.organizers USING btree (organizable_type, organizable_id);


--
-- Name: organizers_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX organizers_status_index ON public.organizers USING btree (status);


--
-- Name: ownership_types_name_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ownership_types_name_index ON public.ownership_types USING btree (name);


--
-- Name: parse_profiles_source_id_entity_type_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX parse_profiles_source_id_entity_type_index ON public.parse_profiles USING btree (source_id, entity_type);


--
-- Name: services_name_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX services_name_index ON public.services USING btree (name);


--
-- Name: sessions_last_activity_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sessions_last_activity_index ON public.sessions USING btree (last_activity);


--
-- Name: sessions_user_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sessions_user_id_index ON public.sessions USING btree (user_id);


--
-- Name: sources_is_active_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sources_is_active_index ON public.sources USING btree (is_active);


--
-- Name: sources_kind_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sources_kind_index ON public.sources USING btree (kind);


--
-- Name: sources_last_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sources_last_status_index ON public.sources USING btree (last_status);


--
-- Name: sources_organizer_id_base_url_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX sources_organizer_id_base_url_unique ON public.sources USING btree (organizer_id, base_url) WHERE (organizer_id IS NOT NULL);


--
-- Name: sources_organizer_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sources_organizer_id_index ON public.sources USING btree (organizer_id);


--
-- Name: specialist_profiles_name_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX specialist_profiles_name_index ON public.specialist_profiles USING btree (name);


--
-- Name: suggested_taxonomy_items_dictionary_type_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX suggested_taxonomy_items_dictionary_type_index ON public.suggested_taxonomy_items USING btree (dictionary_type);


--
-- Name: suggested_taxonomy_items_organization_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX suggested_taxonomy_items_organization_id_index ON public.suggested_taxonomy_items USING btree (organization_id);


--
-- Name: suggested_taxonomy_items_source_reference_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX suggested_taxonomy_items_source_reference_index ON public.suggested_taxonomy_items USING btree (source_reference);


--
-- Name: suggested_taxonomy_items_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX suggested_taxonomy_items_status_index ON public.suggested_taxonomy_items USING btree (status);


--
-- Name: target_audience_name_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX target_audience_name_index ON public.target_audience USING btree (name);


--
-- Name: thematic_categories_name_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX thematic_categories_name_index ON public.thematic_categories USING btree (name);


--
-- Name: venues_city_fias_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX venues_city_fias_id_index ON public.venues USING btree (city_fias_id);


--
-- Name: venues_coordinates_gist_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX venues_coordinates_gist_idx ON public.venues USING gist (coordinates);


--
-- Name: venues_fias_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX venues_fias_id_index ON public.venues USING btree (fias_id);


--
-- Name: venues_kladr_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX venues_kladr_id_index ON public.venues USING btree (kladr_id);


--
-- Name: venues_region_code_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX venues_region_code_index ON public.venues USING btree (region_code);


--
-- Name: venues_region_iso_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX venues_region_iso_index ON public.venues USING btree (region_iso);


--
-- Name: articles articles_organization_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_organization_id_foreign FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE SET NULL;


--
-- Name: articles articles_related_service_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_related_service_id_foreign FOREIGN KEY (related_service_id) REFERENCES public.services(id) ON DELETE SET NULL;


--
-- Name: articles articles_related_thematic_category_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_related_thematic_category_id_foreign FOREIGN KEY (related_thematic_category_id) REFERENCES public.thematic_categories(id) ON DELETE SET NULL;


--
-- Name: event_event_categories event_event_categories_event_category_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_event_categories
    ADD CONSTRAINT event_event_categories_event_category_id_foreign FOREIGN KEY (event_category_id) REFERENCES public.event_categories(id) ON DELETE CASCADE;


--
-- Name: event_event_categories event_event_categories_event_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_event_categories
    ADD CONSTRAINT event_event_categories_event_id_foreign FOREIGN KEY (event_id) REFERENCES public.events(id) ON DELETE CASCADE;


--
-- Name: event_instances event_instances_event_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_instances
    ADD CONSTRAINT event_instances_event_id_foreign FOREIGN KEY (event_id) REFERENCES public.events(id) ON DELETE CASCADE;


--
-- Name: event_venues event_venues_event_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_venues
    ADD CONSTRAINT event_venues_event_id_foreign FOREIGN KEY (event_id) REFERENCES public.events(id) ON DELETE CASCADE;


--
-- Name: event_venues event_venues_venue_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_venues
    ADD CONSTRAINT event_venues_venue_id_foreign FOREIGN KEY (venue_id) REFERENCES public.venues(id) ON DELETE CASCADE;


--
-- Name: events events_organization_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_organization_id_foreign FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE SET NULL;


--
-- Name: events events_organizer_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_organizer_id_foreign FOREIGN KEY (organizer_id) REFERENCES public.organizers(id) ON DELETE CASCADE;


--
-- Name: organization_organization_types organization_organization_types_organization_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_organization_types
    ADD CONSTRAINT organization_organization_types_organization_id_foreign FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: organization_organization_types organization_organization_types_organization_type_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_organization_types
    ADD CONSTRAINT organization_organization_types_organization_type_id_foreign FOREIGN KEY (organization_type_id) REFERENCES public.organization_types(id) ON DELETE CASCADE;


--
-- Name: organization_services organization_services_organization_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_services
    ADD CONSTRAINT organization_services_organization_id_foreign FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: organization_services organization_services_service_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_services
    ADD CONSTRAINT organization_services_service_id_foreign FOREIGN KEY (service_id) REFERENCES public.services(id) ON DELETE CASCADE;


--
-- Name: organization_specialist_profiles organization_specialist_profiles_organization_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_specialist_profiles
    ADD CONSTRAINT organization_specialist_profiles_organization_id_foreign FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: organization_specialist_profiles organization_specialist_profiles_specialist_profile_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_specialist_profiles
    ADD CONSTRAINT organization_specialist_profiles_specialist_profile_id_foreign FOREIGN KEY (specialist_profile_id) REFERENCES public.specialist_profiles(id) ON DELETE CASCADE;


--
-- Name: organization_thematic_categories organization_thematic_categories_organization_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_thematic_categories
    ADD CONSTRAINT organization_thematic_categories_organization_id_foreign FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: organization_thematic_categories organization_thematic_categories_thematic_category_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_thematic_categories
    ADD CONSTRAINT organization_thematic_categories_thematic_category_id_foreign FOREIGN KEY (thematic_category_id) REFERENCES public.thematic_categories(id) ON DELETE CASCADE;


--
-- Name: organization_venues organization_venues_organization_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_venues
    ADD CONSTRAINT organization_venues_organization_id_foreign FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: organization_venues organization_venues_venue_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_venues
    ADD CONSTRAINT organization_venues_venue_id_foreign FOREIGN KEY (venue_id) REFERENCES public.venues(id) ON DELETE CASCADE;


--
-- Name: organizations organizations_coverage_level_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_coverage_level_id_foreign FOREIGN KEY (coverage_level_id) REFERENCES public.coverage_levels(id) ON DELETE SET NULL;


--
-- Name: organizations organizations_ownership_type_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_ownership_type_id_foreign FOREIGN KEY (ownership_type_id) REFERENCES public.ownership_types(id) ON DELETE SET NULL;


--
-- Name: parse_profiles parse_profiles_source_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parse_profiles
    ADD CONSTRAINT parse_profiles_source_id_foreign FOREIGN KEY (source_id) REFERENCES public.sources(id) ON DELETE CASCADE;


--
-- Name: role_user role_user_role_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_user
    ADD CONSTRAINT role_user_role_id_foreign FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: role_user role_user_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_user
    ADD CONSTRAINT role_user_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: services services_parent_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services
    ADD CONSTRAINT services_parent_id_foreign FOREIGN KEY (parent_id) REFERENCES public.services(id) ON DELETE SET NULL;


--
-- Name: sources sources_organizer_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_organizer_id_foreign FOREIGN KEY (organizer_id) REFERENCES public.organizers(id) ON DELETE SET NULL;


--
-- Name: suggested_taxonomy_items suggested_taxonomy_items_organization_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggested_taxonomy_items
    ADD CONSTRAINT suggested_taxonomy_items_organization_id_foreign FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: thematic_categories thematic_categories_parent_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thematic_categories
    ADD CONSTRAINT thematic_categories_parent_id_foreign FOREIGN KEY (parent_id) REFERENCES public.thematic_categories(id) ON DELETE SET NULL;


--
-- Name: user_organizer user_organizer_organizer_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizer
    ADD CONSTRAINT user_organizer_organizer_id_foreign FOREIGN KEY (organizer_id) REFERENCES public.organizers(id) ON DELETE CASCADE;


--
-- Name: user_organizer user_organizer_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizer
    ADD CONSTRAINT user_organizer_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict EDqqaHmb1ccxxxyna1KkQXFvDnoXJL5EJTjIqIcS9JtqhSwEKmnqe5estFBEyhm

--
-- PostgreSQL database dump
--

\restrict IZ4yO9X7AphZn75uLL4ktyDWrJLWeKWeq7BI0YumO1gbT5U7jdCmBPDdHc9Ayik

-- Dumped from database version 18.2 (Homebrew)
-- Dumped by pg_dump version 18.2 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: migrations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.migrations (id, migration, batch) FROM stdin;
1	0001_01_01_000000_create_users_table	1
2	0001_01_01_000001_create_cache_table	1
3	0001_01_01_000002_create_jobs_table	1
4	0001_01_01_000003_create_thematic_categories_table	1
5	0001_01_01_000004_create_services_table	1
6	0001_01_01_000005_create_organization_types_table	1
7	0001_01_01_000006_create_ownership_types_table	1
8	0001_01_01_000007_create_coverage_levels_table	1
9	0001_01_01_000008_create_event_categories_table	1
10	0001_01_01_000009_create_target_audience_table	1
11	0001_01_01_000010_create_organizations_table	1
12	0001_01_01_000011_create_initiative_groups_table	1
13	0001_01_01_000012_create_individuals_table	1
14	0001_01_01_000013_create_organizers_table	1
15	0001_01_01_000014_create_venues_table	1
16	0001_01_01_000015_create_organization_venues_table	1
17	0001_01_01_000016_create_events_table	1
18	0001_01_01_000017_create_event_instances_table	1
19	0001_01_01_000018_create_event_venues_table	1
20	0001_01_01_000019_create_organization_thematic_categories_table	1
21	0001_01_01_000020_create_organization_services_table	1
22	0001_01_01_000021_create_event_event_categories_table	1
23	0001_01_01_000022_create_articles_table	1
24	0001_01_01_000023_create_roles_table	1
25	0001_01_01_000024_create_role_user_table	1
26	0001_01_01_000025_create_user_organizer_table	1
27	0001_01_01_000026_create_sources_table	1
28	0001_01_01_000027_create_parse_profiles_table	1
29	0001_01_01_000028_create_specialist_profiles_table	1
30	0001_01_01_000029_create_organization_organization_types_table	1
31	0001_01_01_000030_create_organization_specialist_profiles_table	1
32	2026_02_18_193020_add_organizer_id_to_sources_table	1
33	2026_02_19_082809_add_fias_level_to_venues_table	2
34	2026_02_19_091544_add_city_fias_id_to_venues_table	3
35	2026_02_19_093721_backfill_city_fias_id_for_federal_cities	4
36	2026_02_19_102227_backfill_city_fias_id_for_level6_settlements	5
37	2026_02_19_102245_backfill_city_fias_id_for_level1_regions	6
38	2026_02_19_124354_add_region_code_to_venues_table	7
40	2026_02_19_124858_backfill_region_code_for_new_regions	8
42	2026_02_19_125127_backfill_region_code_for_cities_and_settlements	9
43	2026_02_20_105753_update_organizers_morph_map_to_short_names	10
44	2026_02_20_151808_allow_same_base_url_per_organizer_in_sources	11
45	2026_02_22_120000_extend_ontology_fields	12
46	2026_02_22_130000_add_description_keywords_to_ownership_types	13
47	2026_02_25_092349_add_source_reference_to_organizations_and_events	14
48	2026_02_25_092353_add_short_title_to_organizations	14
49	2026_02_25_093854_create_suggested_taxonomy_items_table	15
50	2026_02_26_073726_add_event_page_url_and_support_single_occurrence_to_events	16
51	2026_03_03_071516_backfill_sources_last_crawled_and_crawl_period	17
\.


--
-- Name: migrations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.migrations_id_seq', 51, true);


--
-- PostgreSQL database dump complete
--

\unrestrict IZ4yO9X7AphZn75uLL4ktyDWrJLWeKWeq7BI0YumO1gbT5U7jdCmBPDdHc9Ayik

