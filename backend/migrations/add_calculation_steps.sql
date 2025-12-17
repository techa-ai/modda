-- =====================================================
-- Calculation Steps Table
-- Stores individual steps from attribute calculations
-- Enables robust filtering by step_id instead of value matching
-- =====================================================

-- Create calculation_steps table
CREATE TABLE IF NOT EXISTS calculation_steps (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    attribute_id INTEGER NOT NULL REFERENCES form_1008_attributes(id),
    
    -- Step identification
    step_order INTEGER NOT NULL,  -- Order within the calculation (1, 2, 3...)
    
    -- Value information
    value TEXT,                   -- The actual value (e.g., "$1,585,000")
    description TEXT,             -- What this step represents (e.g., "Initial Purchase Price")
    rationale TEXT,               -- Why this value is used
    formula TEXT,                 -- If calculated, the formula (e.g., "$1,595,000 - $1,585,000")
    
    -- Source document information
    document_id INTEGER,          -- References document_analysis.id
    document_name TEXT,           -- Filename for quick reference
    page_number INTEGER,          -- Page where value is found
    source_location TEXT,         -- Specific location (e.g., "Section 3, Paragraph 2")
    
    -- Metadata
    is_calculated BOOLEAN DEFAULT FALSE,  -- True if this is a calculated/derived value
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure unique step order per attribute per loan
    UNIQUE(loan_id, attribute_id, step_order)
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_calc_steps_loan ON calculation_steps(loan_id);
CREATE INDEX IF NOT EXISTS idx_calc_steps_attribute ON calculation_steps(attribute_id);
CREATE INDEX IF NOT EXISTS idx_calc_steps_document ON calculation_steps(document_id);
CREATE INDEX IF NOT EXISTS idx_calc_steps_doc_name ON calculation_steps(document_name);

-- Add comments
COMMENT ON TABLE calculation_steps IS 'Stores individual calculation steps for 1008 attributes, enabling robust document-to-attribute linking';
COMMENT ON COLUMN calculation_steps.step_order IS 'Order within the calculation (1=first step, 2=second, etc.)';
COMMENT ON COLUMN calculation_steps.is_calculated IS 'True if this step is a formula/derived value, not from a document';

