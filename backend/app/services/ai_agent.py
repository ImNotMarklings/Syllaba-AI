import os
import logging
from typing import List, Dict, Any
from google import genai
from google.genai import types
from google.genai.errors import APIError
from app.services.google_service import GoogleService

logger = logging.getLogger(__name__)

FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite"
]

class AIAgentService:
    @staticmethod
    def get_client():
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is missing")
        return genai.Client(api_key=api_key)

    @classmethod
    def _generate_with_fallback(cls, client: genai.Client, contents: list, config: types.GenerateContentConfig):
        """
        Helper method just to test the generation using primary models and give a fallback
        for the other models if error occured. (e.g. Rate Limit, Overload).
        """
        last_exception = None

        for model_name in FALLBACK_MODELS:
            try:
                logger.info(f"Trying Model: {model_name}")
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
                return response, model_name

            except APIError as e:
                logger.warning(f"API Error on model {model_name} (Code {e.code}): {e.message}")
                if e.code == 400:
                    raise e

            except Exception as e:
                logger.error(f"Unexpected error on model {model_name}: {str(e)}")
                last_exception = e

        logger.critical(f"Unexpected error on model {model_name}: {str(e)}")
        raise RuntimeError(f"All Gemini models failed. Last error: {str(last_exception)}")

    @classmethod
    def run_chat_session(cls, user_message: str, chat_history: List[Dict[str, str]] = None, access_token: str = "", refresh_token: str = None) -> str:
        """
        Runs a multi-turn conversational turn with Gemini with full chat history memory.
        Automatically executes tool calls when needed.
        """
        client = cls.get_client()

        # 1. Define python functions that Gemini can invoke as tools
        def get_my_courses() -> List[Dict[str, Any]]:
            """"Fetches all active enrolled Google Classroom courses for the student."""
            return GoogleService.fetch_courses(access_token=access_token, refresh_token=refresh_token)

        def get_course_assignments(course_id: str) -> List[Dict[str, Any]]:
            """
            Fetches all pending assignments, homework, and due dates for a specific course ID.
            Args:
                course_id: The unique ID string of the course.
            """
            return GoogleService.fetch_assignments(
                access_token=access_token,
                course_id=course_id,
                refresh_token=refresh_token
            )

        def get_course_announcements(course_id: str) -> List[Dict[str, Any]]:
            """
            Fetches announcements, posts, and updates from the teacher in a specific course.
            Args:
                course_id: The unique ID string of the course.
            """
            return GoogleService.fetch_announcements(
                access_token=access_token,
                course_id=course_id,
                refresh_token=refresh_token
            )

        def get_course_materials(course_id: str) -> List[Dict[str, Any]]:
            """
            Fetches learning materials, modules, PDFs, and reading resources for a specific course.
            Args:
                course_id: The unique ID string of the course.
            """
            return GoogleService.fetch_material(
                access_token=access_token,
                course_id=course_id,
                refresh_token=refresh_token
            )

        # Map tool name to Python callables
        tools_map = {
            "get_my_courses": get_my_courses,
            "get_course_assignments": get_course_assignments,
            "get_course_announcements": get_course_announcements,
            "get_course_materials": get_course_materials
        }

        system_instruction = """
        You are GClassAIAgent, a friendly, intelligent academic assistant and study mentor for students.
        You have direct access to tools that fetch live Google Classroom data:
        - Use `get_my_courses` when the user asks about their subjects, classes, or enrolled courses.
        - Use `get_course_assignments` when they ask about homework, pending tasks, due dates, or study plans.
        - Use `get_course_announcements` when they ask about announcements, class updates, or teaching notices.
        - Use `get_course_materials` when they ask about modules, reading materials, PDFs, or learning resources.

        Guidelines:
        1. Remember context from previous messages in the conversation history.
        2. When creating a study plan or summary, first call `get_my_courses`. If you need specific coursework deadlines, fetch the assignments for those courses as well.
        3. Format your responses with clear Markdown headings, bullet points, and tables where applicable
        4. Be encouraging, professional, clear, and proactive.
        """

        # 2. Build contents including past conversation history
        contents = []
        if chat_history:
            for msg in chat_history:
                role = "user" if msg.get("role") == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg.get("content", ""))]
                    )
                )

        # Append the current incoming user message
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)]
            )
        )

        # 3. Start Gemini session with tools enabled
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[get_my_courses, get_course_assignments, get_course_announcements, get_course_materials],
            temperature=0.3
        )

        # response = client.models.generate_content(
        #     model=MODEL_NAME,
        #     contents=contents,
        #     config=config
        # )
        response, used_model = cls._generate_with_fallback(client, contents, config)

        # 4. Handle Tool Executions (Automatic Function Calling loop)
        # while response.function_calls:
        #     function_responses = []
        #     for call in response.function_calls:
        #         func_name = call.name
        #         func_args = call.args or {}

        #         if func_name in tools_map:
        #             # Run the tool locally
        #             tool_result = tools_map[func_name](**func_args)

        #             # Prepare function response payload for Gemini
        #             function_responses.append(
        #                 types.Part.from_function_response(
        #                     name=func_name,
        #                     response={"result": tool_result}
        #                 )
        #             )

        while response.function_calls:
            function_responses = []

            for call in response.function_calls:
                func_name = call.name
                func_args = call.args or {}

                if func_name in tools_map:
                    try:
                        tool_result = tools_map[func_name](**func_args)
                    except Exception as e:
                        logger.error(f"Error executing tool {func_name}: {err}")
                        tool_result = {"error": f"Failed to fetch data: {str(e)}"}

                    function_responses.append(
                        types.Part.from_function_response(
                            name=func_name,
                            response={"result": tool_result}
                        )
                    )

            # Append the model's tool call candidate and function execution results
            # contents.append(response.candidates[0].content)
            # contents.extend(function_responses)
            contents.append(response.candidates[0].content)
            contents.append(
                types.Content(
                    role="user",
                    parts=function_responses
                )
            )

            # # Send function execution results back to Gemini for final responses synthesis
            # response = client.models.generate_content(
            #     model=MODEL_NAME,
            #     contents=contents,
            #     config=config
            # )
            response, used_model = cls._generate_with_fallback(client, contents, config)

        return response.text
