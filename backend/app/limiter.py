# app/limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

# Function to get identifier of request (IP Address or Authorization token)
def get_user_identifier(request: Request) -> str:
    # 1. Try to use the Auth header / Bearer token if have user login
    auth_header = request.headers.get("Authorization")
    if auth_header:
        return auth_header.replace("Bearer ", "").strip()

    # 2. If guest, use IP Address
    return get_remote_address(request)

limiter = Limiter(
    key_func=get_user_identifier,
    default_limits=["100 per day", "30 per hour"]
)
