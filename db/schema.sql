-- mailwatch-agent schema (Neon / Postgres)

create extension if not exists pgcrypto;

-- Tracks the Gmail History API cursor so polling never re-scans or misses messages.
create table if not exists poll_state (
    id smallint primary key default 1,
    last_history_id text,
    updated_at timestamptz not null default now(),
    constraint poll_state_singleton check (id = 1)
);

-- Every Gmail message ID we've already processed, so a later poll never re-handles it.
create table if not exists processed_messages (
    gmail_message_id text primary key,
    processed_at timestamptz not null default now()
);

-- One row per real email that's been drafted and posted to Discord for approval.
create table if not exists pending_approvals (
    id uuid primary key default gen_random_uuid(),
    gmail_message_id text not null unique,
    discord_message_id text,
    sender text not null,
    subject text,
    excerpt text,
    draft_text text,
    status text not null default 'pending'
        check (status in ('pending', 'approved', 'sent', 'expired')),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    last_reminder_at timestamptz
);

-- Record of what was actually sent, for review.
create table if not exists sent_replies (
    id uuid primary key default gen_random_uuid(),
    gmail_message_id text not null,
    sent_text text not null,
    sent_via text not null check (sent_via in ('approved_draft', 'custom_text')),
    sent_at timestamptz not null default now()
);

-- Sender-level filtering config: manual block list plus always-skip / always-draft
-- overrides set from Discord buttons. Scope applies either to one address or a
-- whole domain.
create table if not exists sender_rules (
    id uuid primary key default gen_random_uuid(),
    scope text not null check (scope in ('address', 'domain')),
    value text not null,
    rule_type text not null check (rule_type in ('block', 'always_skip', 'always_draft')),
    created_at timestamptz not null default now(),
    unique (scope, value, rule_type)
);

-- Subject/sender-name phrases that force a skip regardless of other signals.
-- Grows over time as Azka spots more false positives, without a redeploy.
create table if not exists keyword_rules (
    id uuid primary key default gen_random_uuid(),
    keyword text not null unique,
    created_at timestamptz not null default now()
);

create index if not exists idx_pending_approvals_status on pending_approvals (status);
create index if not exists idx_sender_rules_value on sender_rules (value);

insert into keyword_rules (keyword) values
    ('job alert'), ('jobs for you'), ('new jobs'), ('new job matches'),
    ('your application'), ('job recommendation'), ('job match'),
    ('unsubscribe'), ('weekly digest'), ('daily digest'), ('notification digest'),
    ('newsletter')
on conflict (keyword) do nothing;
