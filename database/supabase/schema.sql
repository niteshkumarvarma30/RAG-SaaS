-- Enable vector extension for pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Create tenants table
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create documents table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create document_chunks table (Matryoshka embeddings typically output 1536, 1024, or 512 dims)
-- We'll assume a standard 1536 initially.
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding VECTOR(1536), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;

-- Idiomatic Supabase RLS Policies using custom JWT claims
-- This ensures that only requests carrying a JWT with the correct 'tenant_id' can access the data.

CREATE POLICY "Tenant Isolation" ON documents
    AS PERMISSIVE FOR ALL
    USING (tenant_id::text = (current_setting('request.jwt.claims', true)::json->>'tenant_id'))
    WITH CHECK (tenant_id::text = (current_setting('request.jwt.claims', true)::json->>'tenant_id'));

CREATE POLICY "Tenant Isolation" ON document_chunks
    AS PERMISSIVE FOR ALL
    USING (tenant_id::text = (current_setting('request.jwt.claims', true)::json->>'tenant_id'))
    WITH CHECK (tenant_id::text = (current_setting('request.jwt.claims', true)::json->>'tenant_id'));
