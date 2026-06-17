import os
import jwt
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

class SupabaseManager:
    def __init__(self):
        self.url = os.environ.get("SUPABASE_URL", "")
        # We use the anon key. The custom JWT handles the permissions.
        self.key = os.environ.get("SUPABASE_KEY", "")
        self.service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", "")
        
        if not self.url or not self.key or not self.service_role_key:
            raise ValueError("SUPABASE_URL, SUPABASE_KEY, and SUPABASE_SERVICE_ROLE_KEY must be provided.")
        
        # Admin client uses the service_role key to bypass all RLS policies
        self._admin_client: Client = create_client(self.url, self.service_role_key)

    def get_admin_client(self) -> Client:
        """Returns the admin client initialized with the service_role key. Bypasses RLS."""
        return self._admin_client
    
    def get_tenant_client(self, tenant_id: str) -> Client:
        """
        Creates a custom signed JWT containing the tenant_id, and attaches it to a new client.
        This forces Postgres to apply the RLS policies in schema.sql.
        """
        if not self.jwt_secret:
            raise ValueError("SUPABASE_JWT_SECRET is required to sign tenant tokens.")

        payload = {
            "role": "authenticated", # Must be 'authenticated' to bypass anon RLS limits
            "tenant_id": tenant_id,
            "sub": tenant_id # This maps to auth.uid() in Postgres
        }
        
        # Sign the JWT with the Supabase JWT secret
        encoded_jwt = jwt.encode(payload, self.jwt_secret, algorithm="HS256")
        
        client = create_client(self.url, self.key)
        # Set the auth header to our custom JWT
        client.options.headers.update({
            "Authorization": f"Bearer {encoded_jwt}"
        })
        
        return client

supabase_manager = SupabaseManager()
