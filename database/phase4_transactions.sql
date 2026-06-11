-- Phase 4: Create transactions table for metered billing
-- Run this in your Supabase SQL Editor!

CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    tokens_used INT NOT NULL,
    status TEXT DEFAULT 'pending_billing'
);

-- Enable RLS
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

-- Tenant Isolation Policy
CREATE POLICY "Tenants can only view their own transactions"
ON transactions FOR SELECT
USING (auth.uid() = tenant_id);
