-- Add source tracking to evidence_files table
-- This distinguishes between 1008, URLA, and other document sources

ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS source_document VARCHAR(255);
ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS source_type VARCHAR(50);
ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS document_id INTEGER;
ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50);
ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS confidence_score DECIMAL(5,2);

-- Create index for source queries
CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence_files(source_document, source_type);

-- Update existing records to mark URLA sources
UPDATE evidence_files 
SET source_document = '1008 Transmittal Form',
    source_type = '1008'
WHERE file_name LIKE '%1008%' 
  AND source_document IS NULL;

UPDATE evidence_files 
SET source_document = 'URLA (Fallback)',
    source_type = 'URLA'
WHERE file_name LIKE '%urla%' 
  AND source_document IS NULL;

-- Set default source type for remaining records
UPDATE evidence_files 
SET source_type = 'SUPPORTING'
WHERE source_type IS NULL;

