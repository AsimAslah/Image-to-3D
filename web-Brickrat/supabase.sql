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
  created_at timestamptz not null default now()
);

-- Run these migration statements too when the products table already exists.
alter table public.products add column if not exists image_sha256 text;
create unique index if not exists products_image_sha256_key
  on public.products (image_sha256)
  where image_sha256 is not null;

alter table public.products enable row level security;

-- Prefer the service-role key on a trusted server. For an anon key, add narrowly
-- scoped insert/select policies appropriate for your authentication model.
