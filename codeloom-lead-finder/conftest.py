"""
conftest.py — pytest configuration
────────────────────────────────────
Sets dummy environment variables before any backend module is imported,
so tests can run without a real .env file, MySQL, or OpenAI key.
"""
import os

# Must be set before backend.config is imported
os.environ.setdefault("OPENAI_API_KEY",   "sk-test-dummy-key")
os.environ.setdefault("MYSQL_PASSWORD",   "test_password")
os.environ.setdefault("MYSQL_DATABASE",   "codeloom_leads_test")
os.environ.setdefault("MYSQL_HOST",       "localhost")
os.environ.setdefault("MYSQL_USER",       "root")
os.environ.setdefault("MYSQL_PORT",       "3306")
os.environ.setdefault("CSV_EXPORT_DIR",   "data")
os.environ.setdefault("OPENAI_MODEL",     "gpt-4o-mini")
os.environ.setdefault("BACKEND_HOST",     "127.0.0.1")
os.environ.setdefault("BACKEND_PORT",     "8000")
os.environ.setdefault("AUTOMATION_HEADLESS", "true")
os.environ.setdefault("AUTOMATION_SLOW_MO",  "0")
