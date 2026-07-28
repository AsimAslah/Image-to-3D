-- Run this in the Supabase SQL editor, then create a public Storage bucket named "products".
create table if not exists public.products (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  category text not null,
  subcategory text not null,
  description text not null default '',
  price numeric(12, 2),
  image_url text not null,
  image_sha256 text not null,
  obj_url text not null,
  model_url text not null,
  usdz_url text,
  width double precision not null,
  height double precision not null,
  depth double precision not null,
  original_unit text not null,
  width_m double precision not null,
  height_m double precision not null,
  depth_m double precision not null,
  scaling_mode text not null,
  applied_scale_factors jsonb not null,
  axis_mapping jsonb not null,
  model_orientation text not null,
  final_dimensions_m jsonb not null,
  room_dimensions jsonb,
  fit_result jsonb,
  created_at timestamptz not null default now()
);

-- Run these migration statements too when the products table already exists.
alter table public.products add column if not exists image_sha256 text;
alter table public.products add column if not exists usdz_url text;
alter table public.products add column if not exists width double precision;
alter table public.products add column if not exists height double precision;
alter table public.products add column if not exists depth double precision;
alter table public.products add column if not exists original_unit text;
alter table public.products add column if not exists width_m double precision;
alter table public.products add column if not exists height_m double precision;
alter table public.products add column if not exists depth_m double precision;
alter table public.products add column if not exists scaling_mode text;
alter table public.products add column if not exists applied_scale_factors jsonb;
alter table public.products add column if not exists axis_mapping jsonb;
alter table public.products add column if not exists model_orientation text;
alter table public.products add column if not exists final_dimensions_m jsonb;
alter table public.products add column if not exists room_dimensions jsonb;
alter table public.products add column if not exists fit_result jsonb;
create unique index if not exists products_image_sha256_key
  on public.products (image_sha256)
  where image_sha256 is not null;

alter table public.products enable row level security;

-- Prefer the service-role key on a trusted server. For an anon key, add narrowly
-- scoped insert/select policies appropriate for your authentication model.
