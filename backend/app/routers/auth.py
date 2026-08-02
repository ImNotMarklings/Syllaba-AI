from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from sqlalchemy.orm import Session
from fastapi.responses import RedirectResponse
import os

from app.database import get_db
from app.models import User
from app.services.google_service import GoogleService

router = APIRouter(prefix="/auth", tags=["Authentication"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

@router.get("/login")
def google_login():
    """Generates the Google OAuth authorization URL for user login"""
    try:
        flow = GoogleService.create_oauth_flow()
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        return {"authorization_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/callback")
def google_callback(
    code: str = Query(..., description="The authorization code sent back by Google"),
    db: Session = Depends(get_db)
):
    """
    Exchanges Google authorization code for tokens, fetches user profile,
    and saves/updates the user in the database
    """
    try:
        # 1. Exchange code for tokens using Google OAuth Flow
        flow = GoogleService.create_oauth_flow()
        flow.oauth2session.scope = None
        flow.fetch_token(code=code)
        credentials = flow.credentials

        access_token = credentials.token
        refresh_token = credentials.refresh_token

        # 2. Fetch user profile from Google using the new access token
        profile = GoogleService.fetch_user_profile(access_token)
        google_id = profile.get("id")
        email = profile.get("email")
        name = profile.get("name")
        picture = profile.get("picture")

        # Check if user exists in the database
        user = db.query(User).filter(User.google_id == google_id).first()

        if not user:
            # Create new user record
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                picture=picture,
                access_token=access_token,
                refresh_token=refresh_token
            )
            db.add(user)
        else:
            # Updating existing user tokens & profile info
            user.access_token = access_token
            if refresh_token:
                user.refresh_token = refresh_token
            user.name = name
            user.picture = picture

        # 4. Save changes to database
        db.commit()
        db.refresh(user)

        # 3. Redirect directly to the App page
        response = RedirectResponse(url=f"{FRONTEND_URL}/app/chat")

        # 4. Set HttpOnly Cookie
        response.set_cookie(
            key="syllaba_session",
            value=str(user.id),
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=60 * 60 * 24 * 7 # = 7 days validity
        )
        
        return response
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")

@router.get("/me")
def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Fetches the profile of the currently logged-in user
    using the HttpOnly session cookie.
    """
    user_id = request.cookies.get("syllaba_session")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "access_token": user.access_token
    }

@router.post("/logout")
def logout(response: Response):
    """Deletes the HttpOnly session cookie to log the user out."""
    response.delete_cookie(
        key="syllaba_session",
        httponly=True,
        samesite="lax"
    )
    return {"message": "Logged out succesfully"}