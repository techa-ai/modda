-- Database migration: Add document_analysis table to store deduplication results

CREATE TABLE IF NOT EXISTS document_analysis (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loans(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    file_path TEXT NOT NULL,
    file_size BIGINT,
    page_count INTEGER,
    text_hash VARCHAR(64),
    status VARCHAR(50) NOT NULL,
    master_document_id INTEGER REFERENCES document_analysis(id),
    duplicate_count INTEGER DEFAULT 0,
    upload_date TIMESTAMP,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(loan_id, filename)
);

CREATE INDEX IF NOT EXISTS idx_document_analysis_loan_id ON document_analysis(loan_id);
CREATE INDEX IF NOT EXISTS idx_document_analysis_text_hash ON document_analysis(text_hash);
CREATE INDEX IF NOT EXISTS idx_document_analysis_status ON document_analysis(status);

ALTER TABLE loans ADD COLUMN IF NOT EXISTS dedup_status VARCHAR(50) DEFAULT 'pending';
ALTER TABLE loans ADD COLUMN IF NOT EXISTS dedup_last_run TIMESTAMP;
