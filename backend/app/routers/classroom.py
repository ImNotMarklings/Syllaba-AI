from fastapi import APIRouter, Header, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.services.google_service import GoogleService

router = APIRouter(prefix="/classroom", tags=["Google Classroom"])

def get_google_token(
    authorization: str = Header(None),
    request: Request = None,
    db: Session = Depends(get_db)
) -> str:
    """Helper function to derive Google Access Token either from Header or Session Cookie"""
    token = None

    # 1. Try to get from Authorization header
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()

    # 2. If not on header, get from cookie and find the token on database
    if not token and request:
        user_id = request.cookies.get("syllaba_session")
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                token = user.access_token

    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    return token
    

@router.get("/courses")
def get_courses(authorization: str = Header(...), request: Request = None, db: Session = Depends(get_db)):
    """Fetch all active courses for the student"""
    try:
        token = get_google_token(authorization=authorization, request=request, db=db)
        courses = GoogleService.fetch_courses(access_token=token)
        return {"courses": courses}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch courses: {str(e)}")

@router.get("/courses/{course_id}/assignments")
def get_course_assignments(course_id: str, authorization: str = Header(...), request: Request = None, db: Session = Depends(get_db)):
    """Fetch all assignment on a specific active course for the student"""
    try:
        token = get_google_token(authorization=authorization, request=request, db=db)
        assignments = GoogleService.fetch_assignments(access_token=token, course_id=course_id)
        return {"course_id": course_id, "assignments": assignments}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch assignments: {str(e)}")