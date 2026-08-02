from app.database import engine, Base
from app.models import User, Conversation, ChatMessage

def init_database():
    print("[~] Connecting to Aiven PostgreSQL Database...")
    try:
        # Force to make tables
        Base.metadata.create_all(bind=engine)
        print("[+] Success created tables")
    except Exception as e:
        print(f"[-] Failed to create tables:\n{e}")

if __name__ == "__main__":
    init_database()