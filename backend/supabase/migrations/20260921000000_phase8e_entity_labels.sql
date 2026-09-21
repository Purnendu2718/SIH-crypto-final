-- Phase 8E: GraphSense TagPacks & Worldwide Label Coverage Migration
-- Table: entities (organization and actor metadata)
CREATE TABLE IF NOT EXISTS public.entities (
    id TEXT PRIMARY KEY,
    actor_id TEXT UNIQUE NOT NULL,
    label TEXT NOT NULL,
    categories JSONB DEFAULT '[]'::jsonb,
    uri TEXT,
    jurisdictions JSONB DEFAULT '[]'::jsonb,
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entities_actor_id ON public.entities (actor_id);

-- Table: entity_labels (cryptocurrency address attribution tags)
CREATE TABLE IF NOT EXISTS public.entity_labels (
    id TEXT PRIMARY KEY,
    address TEXT NOT NULL,
    chain TEXT NOT NULL,
    label TEXT NOT NULL,
    actor_id TEXT REFERENCES public.entities(actor_id) ON DELETE SET NULL,
    source_url TEXT,
    last_modified TIMESTAMPTZ,
    tag_source TEXT DEFAULT 'GRAPHSENSE_TAGPACK',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_labels_address ON public.entity_labels (address);
CREATE INDEX IF NOT EXISTS idx_entity_labels_chain ON public.entity_labels (chain);
CREATE INDEX IF NOT EXISTS idx_entity_labels_actor_id ON public.entity_labels (actor_id);

-- Table: tagpack_sync_status (sync history and metadata)
CREATE TABLE IF NOT EXISTS public.tagpack_sync_status (
    id TEXT PRIMARY KEY,
    last_synced_at TIMESTAMPTZ DEFAULT NOW(),
    total_actors INTEGER DEFAULT 0,
    total_labels INTEGER DEFAULT 0,
    source TEXT DEFAULT 'GITHUB_GRAPHSENSE_TAGPACKS',
    status TEXT DEFAULT 'COMPLETED',
    error_message TEXT
);

-- Alter attributions table to store entity_category
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'attributions' AND column_name = 'entity_category'
    ) THEN
        ALTER TABLE public.attributions ADD COLUMN entity_category TEXT;
    END IF;
END $$;
