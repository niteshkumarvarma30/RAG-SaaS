-- Phase 3: Hybrid Search RPC for Supabase (Cosine Similarity)
-- Drop the conflicting functions first!
DROP FUNCTION IF EXISTS match_document_chunks(vector(1536), integer, text);
DROP FUNCTION IF EXISTS match_document_chunks(vector(1536), integer, uuid);

-- Now create the correct one
CREATE OR REPLACE FUNCTION match_document_chunks (
  query_embedding vector(1536),
  match_count int DEFAULT 10,
  p_tenant_id uuid DEFAULT NULL
) RETURNS TABLE (
  id uuid,
  content text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    dc.id,
    dc.content,
    1 - (dc.embedding <=> query_embedding) AS similarity
  FROM document_chunks dc
  WHERE dc.tenant_id = p_tenant_id
  ORDER BY dc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
