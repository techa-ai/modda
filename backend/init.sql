-- MODDA Database Schema

-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'user')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Loans table
CREATE TABLE loans (
    id SERIAL PRIMARY KEY,
    loan_number VARCHAR(100) UNIQUE NOT NULL,
    loan_name VARCHAR(255),
    document_location TEXT,
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    assigned_to INTEGER REFERENCES users(id),
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 1008 Form Attributes table (defines standard fields)
CREATE TABLE form_1008_attributes (
    id SERIAL PRIMARY KEY,
    attribute_name VARCHAR(255) NOT NULL,
    attribute_label VARCHAR(255) NOT NULL,
    data_type VARCHAR(50) DEFAULT 'text',
    is_required BOOLEAN DEFAULT false,
    section VARCHAR(100),
    display_order INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Evidence Documents table (acceptable evidence for each attribute)
CREATE TABLE evidence_documents (
    id SERIAL PRIMARY KEY,
    attribute_id INTEGER REFERENCES form_1008_attributes(id) ON DELETE CASCADE,
    document_type VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Extracted 1008 Data table
CREATE TABLE extracted_1008_data (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loans(id) ON DELETE CASCADE,
    attribute_id INTEGER REFERENCES form_1008_attributes(id),
    extracted_value TEXT,
    confidence_score DECIMAL(5,2),
    extraction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    document_path TEXT,
    page_number INTEGER
);

-- Evidence Files table
CREATE TABLE evidence_files (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loans(id) ON DELETE CASCADE,
    attribute_id INTEGER REFERENCES form_1008_attributes(id),
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(100),
    is_secured BOOLEAN DEFAULT false,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Processing Logs table
CREATE TABLE processing_logs (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loans(id) ON DELETE CASCADE,
    step VARCHAR(100),
    status VARCHAR(50),
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_loans_assigned_to ON loans(assigned_to);
CREATE INDEX idx_loans_status ON loans(status);
CREATE INDEX idx_extracted_data_loan ON extracted_1008_data(loan_id);
CREATE INDEX idx_evidence_files_loan ON evidence_files(loan_id);
CREATE INDEX idx_processing_logs_loan ON processing_logs(loan_id);

-- Insert default admin user (password: admin123)
INSERT INTO users (username, email, password_hash, role) 
VALUES ('admin', 'admin@modda.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIwNoLaZeu', 'admin');

-- Insert sample 1008 form attributes
INSERT INTO form_1008_attributes (attribute_name, attribute_label, section, display_order) VALUES
('borrower_name', 'Borrower Name', 'Borrower Information', 1),
('co_borrower_name', 'Co-Borrower Name', 'Borrower Information', 2),
('property_address', 'Property Address', 'Property Information', 3),
('loan_amount', 'Loan Amount', 'Loan Information', 4),
('interest_rate', 'Interest Rate', 'Loan Information', 5),
('loan_term', 'Loan Term (months)', 'Loan Information', 6),
('monthly_income', 'Monthly Income', 'Financial Information', 7),
('monthly_debt', 'Monthly Debt', 'Financial Information', 8),
('credit_score', 'Credit Score', 'Financial Information', 9),
('employment_status', 'Employment Status', 'Employment Information', 10),
('employer_name', 'Employer Name', 'Employment Information', 11),
('years_employed', 'Years Employed', 'Employment Information', 12),
('down_payment', 'Down Payment', 'Financial Information', 13),
('property_value', 'Property Value', 'Property Information', 14),
('loan_purpose', 'Loan Purpose', 'Loan Information', 15);

-- Insert sample evidence document types
INSERT INTO evidence_documents (attribute_id, document_type, description) VALUES
(1, 'Government ID', 'Driver License, Passport'),
(1, 'Social Security Card', 'SSN verification'),
(7, 'Pay Stubs', 'Recent 2 months pay stubs'),
(7, 'W2 Forms', 'Last 2 years W2'),
(7, 'Tax Returns', 'Last 2 years tax returns'),
(8, 'Credit Report', 'Credit report showing debts'),
(9, 'Credit Report', 'Credit score verification'),
(10, 'Employment Letter', 'Letter from employer'),
(11, 'Employment Letter', 'Letter from employer'),
(12, 'Employment Letter', 'Letter from employer'),
(13, 'Bank Statements', 'Proof of down payment funds'),
(14, 'Appraisal Report', 'Property appraisal');
