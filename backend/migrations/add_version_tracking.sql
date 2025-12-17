-- Add columns for version tracking and visual deduplication
ALTER TABLE document_analysis ADD COLUMN IF NOT EXISTS visual_phash TEXT;
ALTER TABLE document_analysis ADD COLUMN IF NOT EXISTS visual_dhash TEXT;
ALTER TABLE document_analysis ADD COLUMN IF NOT EXISTS visual_ahash TEXT;
ALTER TABLE document_analysis ADD COLUMN IF NOT EXISTS version_group_id TEXT;
ALTER TABLE document_analysis ADD COLUMN IF NOT EXISTS detected_date DATE;
ALTER TABLE document_analysis ADD COLUMN IF NOT EXISTS is_latest_version BOOLEAN DEFAULT FALSE;
