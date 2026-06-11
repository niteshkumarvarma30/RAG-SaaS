// Ensure Tenant uniqueness
CREATE CONSTRAINT tenant_id_unique IF NOT EXISTS FOR (t:Tenant) REQUIRE t.id IS UNIQUE;

// Ensure Document uniqueness
CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE;

// Indexes for common entities to speed up graph search per tenant
CREATE INDEX entity_tenant_id_index IF NOT EXISTS FOR (e:Entity) ON (e.tenantId);
CREATE INDEX document_tenant_id_index IF NOT EXISTS FOR (d:Document) ON (d.tenantId);
CREATE INDEX chunk_tenant_id_index IF NOT EXISTS FOR (c:Chunk) ON (c.tenantId);
