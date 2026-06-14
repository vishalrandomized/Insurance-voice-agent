create extension if not exists vector;
create extension if not exists pgcrypto;

create type callback_status as enum (
  'not_requested', 'requested', 'in_progress', 'completed', 'cancelled'
);
create type callback_source as enum (
  'customer_voice', 'customer_ui', 'salesperson'
);
create type session_status as enum ('active', 'completed', 'abandoned');

create table products (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now()
);

create table documents (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  filename text not null,
  storage_path text,
  status text not null default 'processing',
  page_count integer,
  created_at timestamptz not null default now()
);

create table document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references documents(id) on delete cascade,
  page_number integer not null,
  section_heading text,
  chunk_index integer not null,
  content text not null,
  embedding vector(1536),
  unique(document_id, page_number, chunk_index)
);

create table sessions (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id),
  status session_status not null default 'active',
  started_at timestamptz not null default now(),
  ended_at timestamptz
);

create table leads (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null unique references sessions(id) on delete cascade,
  customer_name text,
  phone text,
  product_id uuid not null references products(id),
  callback_status callback_status not null default 'not_requested',
  callback_reason text,
  preferred_callback_text text,
  preferred_callback_at timestamptz,
  conversation_summary text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table conversation_turns (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references sessions(id) on delete cascade,
  role text not null check (role in ('customer', 'agent')),
  text text not null,
  citations jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table callback_actions (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references leads(id) on delete cascade,
  status text not null check (status in ('pending', 'confirmed', 'cancelled', 'expired')),
  reason text not null,
  preferred_callback_text text,
  source callback_source not null,
  idempotency_key text not null unique,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table audit_events (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references leads(id) on delete cascade,
  event_type text not null,
  source callback_source not null,
  payload jsonb not null default '{}'::jsonb,
  idempotency_key text unique,
  created_at timestamptz not null default now()
);

create index leads_callback_status_idx on leads(callback_status, updated_at desc);
create index leads_session_id_idx on leads(session_id);
create index chunks_document_id_idx on document_chunks(document_id);
create index turns_session_id_idx on conversation_turns(session_id, created_at);
create index audit_lead_id_idx on audit_events(lead_id, created_at desc);
create index chunks_embedding_idx on document_chunks
using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create or replace function match_document_chunks(
  query_embedding vector(1536),
  target_document_id uuid,
  match_count integer default 5,
  minimum_similarity double precision default 0.08
)
returns table (
  id uuid,
  document_id uuid,
  filename text,
  page_number integer,
  section_heading text,
  chunk_index integer,
  content text,
  similarity double precision
)
language sql stable
as $$
  select
    document_chunks.id,
    document_chunks.document_id,
    documents.filename,
    document_chunks.page_number,
    document_chunks.section_heading,
    document_chunks.chunk_index,
    document_chunks.content,
    1 - (document_chunks.embedding <=> query_embedding) as similarity
  from document_chunks
  join documents on documents.id = document_chunks.document_id
  where document_chunks.document_id = target_document_id
    and 1 - (document_chunks.embedding <=> query_embedding) >= minimum_similarity
  order by document_chunks.embedding <=> query_embedding
  limit match_count;
$$;

alter publication supabase_realtime add table leads;
alter publication supabase_realtime add table audit_events;
