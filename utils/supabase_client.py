from dotenv import load_dotenv
from supabase import create_client, Client
import os

load_dotenv()  # .env 파일에서 환경변수 불러오기

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)