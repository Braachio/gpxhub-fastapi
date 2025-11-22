import os
from functools import lru_cache
from typing import cast

from dotenv import load_dotenv
from supabase import Client, create_client


load_dotenv()


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Return a cached Supabase client initialised from environment variables.
    Raises a ValueError if SUPABASE_URL or SUPABASE_KEY are missing.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in the environment")

    client = create_client(supabase_url, supabase_key)
    return cast(Client, client)

