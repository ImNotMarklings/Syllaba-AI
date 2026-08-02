import os

# Relax scope checking globally for oauthlib
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid"
]

class GoogleService:
    @staticmethod
    def create_oauth_flow():
        """Creates the Google OAuth flow configuration."""
        client_config = {
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }

        redirect_uri = os.getenv("REDIRECT_URI", "https://syllaba-api.onrender.com/auth/callback")

        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=redirect_uri,
            autogenerate_code_verifier=False
        )

        return flow

    @staticmethod
    def get_classroom_client(access_token: str, refresh_token: str = None):
        """
        Initialize a Google Classroom API client.
        Passing full context prevents refresh validation errors.
        """
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            scopes=SCOPES
        )

        # Automatic token refresh check
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}")

        return build('classroom', 'v1', credentials=creds)

    @classmethod
    def fetch_user_profile(cls, access_token: str, refresh_token: str = None) -> dict:
        """
        Fetches basic Google user profile (id, email, name, picture) using OAuth2
        """

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            scopes=SCOPES
        )
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        # Use oauth2 v2 to fetch userinfo
        service = build('oauth2', 'v2', credentials=creds)
        user_info = service.userinfo().get().execute()

        return {
            "id": user_info.get("id"),
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "picture": user_info.get("picture")
        }

    @classmethod
    def fetch_courses(cls, access_token: str, refresh_token: str = None):
        """Fetches active enrolled courses for the logged-in student."""
        service = cls.get_classroom_client(access_token, refresh_token)
        results = service.courses().list(
            studentId='me',
            courseStates=['ACTIVE']
        ).execute()

        courses = results.get('courses', [])
        return [
            {
                "id": c["id"],
                "name": c["name"],
                "section": c.get("section", ""),
                "room": c.get("room", ""),
                "alternateLink": c.get("alternateLink", "")
            }
            for c in courses
        ]

    @classmethod
    def fetch_assignments(cls, access_token: str, course_id: str, refresh_token: str = None):
        """Fetches pending coursework and due dates for a specific course."""
        service = cls.get_classroom_client(access_token, refresh_token)
        results = service.courses().courseWork().list(
            courseId=course_id
        ).execute()

        course_work = results.get('courseWork', [])
        return [
            {
                "id": w["id"],
                "title": w["title"],
                "description": w.get("description", ""),
                "dueDate": w.get("dueDate", {}),
                "dueTime": w.get("dueTime", {}),
                "alternateLink": w.get("alternateLink", "")
            }
            for w in course_work
        ]

    @classmethod
    def fetch_announcements(cls, access_token: str, course_id: str, refresh_token: str = None):
        """Fetches announcement posted in a specific Google Classroom course"""
        service = cls.get_classroom_client(access_token, refresh_token)
        results = service.courses().announcements().list(
            courseId=course_id
        ).execute()

        announcements = results.get('announcements', [])
        return [
            {
                "id": a["id"],
                "text": a.get("text", ""),
                "creationTime": a.get("creationTime", ""),
                "alternateLink": a.get("alternateLink", "")
            }
            for a in announcements
        ]

    @classmethod
    def fetch_material(cls, access_token: str, course_id: str, refresh_token: str = None):
        """Fetches course materials, learning resources, and PDFs uploaded in a course"""
        service = cls.get_classroom_client(access_token, refresh_token)
        results = service.courses().courseWorkMaterials().list(
            courseId=course_id
        ).execute()

        materials = results.get('courseWorkMaterial', [])
        return [
            {
                "id": m["id"],
                "title": m.get("title", ""),
                "description": m.get("description", ""),
                "alternateLink": m.get("alternateLink", ""),
                "materials": m.get("materials", [])
            }
            for m in materials
        ]
