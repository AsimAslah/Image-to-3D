create table if not exists public.render_jobs (
  render_id text primary key
    check (render_id ~ '^R[A-Z0-9]{4,31}$'),
  status text not null
    check (status in ('queued', 'processing', 'completed', 'failed')),
  progress smallint
    check (progress between 0 and 100),
  model_format text
    check (model_format ~ '^[A-Z0-9]{2,12}$'),
  updated_at timestamptz not null
);

alter table public.render_jobs enable row level security;
revoke all on table public.render_jobs from anon, authenticated;
grant select, insert, update on table public.render_jobs to service_role;

comment on table public.render_jobs is
  'Public-safe lifecycle records written by Image-to-3D and read by RenderPulse.';
