-- Fix RLS: Allow inserts into the transactions table
CREATE POLICY "Allow system to insert transactions"
ON transactions FOR INSERT
WITH CHECK (true);
