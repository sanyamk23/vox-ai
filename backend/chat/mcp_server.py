import os
import aiohttp
from typing import Dict, Any


class VoxMCPTools:
    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN", "")

    async def save_candidate_info(self, field: str, value: str) -> Dict[str, Any]:
        return {"status": "saved", "field": field, "value": value}

    async def end_call(self) -> Dict[str, Any]:
        """Signal to the agent to terminate the session."""
        return {"status": "ending"}

    async def get_github_stats(self, username: str) -> Dict[str, Any]:
        if not username:
            return {"error": "No username provided"}
        if self.github_token:
            try:
                headers = {
                    "Authorization": f"token {self.github_token}",
                    "Accept": "application/vnd.github.v3+json",
                }
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"https://api.github.com/users/{username}", headers=headers
                    ) as r:
                        if r.status == 200:
                            d = await r.json()
                            return {
                                "public_repos": d.get("public_repos"),
                                "followers": d.get("followers"),
                                "bio": d.get("bio"),
                            }
            except Exception:
                pass
        return {
            "top_languages": ["Python", "JavaScript"],
            "contributions": "Data unavailable — add GITHUB_TOKEN for live stats",
        }

    async def get_linkedin_assessment(self, profile_url: str) -> Dict[str, Any]:
        return {
            "note": "LinkedIn scraping requires a paid proxy. Stub returned.",
            "profile_url": profile_url,
        }

    async def get_resume_context(self, candidate_id: str) -> Dict[str, Any]:
        return {
            "note": "Resume context lookup not yet connected. Stub returned.",
            "candidate_id": candidate_id,
        }

    def get_tool_definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "save_candidate_info",
                    "description": (
                        "CALL THIS IMMEDIATELY — without pausing the conversation — whenever the candidate "
                        "mentions any concrete fact. This is a silent background save; the user never hears it.\n\n"
                        "CALL IT FOR:\n"
                        "- Salary / CTC: current or expected\n"
                        "- Notice period or joining availability\n"
                        "- Years of experience in a skill or overall\n"
                        "- A specific skill they confirm having\n"
                        "- Current company or role title\n"
                        "- Whether they have competing offers\n"
                        "- Location preference or constraint\n\n"
                        "FIELD NAME CONVENTIONS:\n"
                        "  'current_ctc_lpa'         → current salary (e.g. '18')\n"
                        "  'salary_expected_lpa'      → expected salary (e.g. '25')\n"
                        "  'notice_period'            → e.g. '60_days', 'immediate', '3_months'\n"
                        "  'skill_react'              → 'confirmed' or years e.g. '3_years'\n"
                        "  'skill_python'             → same pattern\n"
                        "  'current_company'          → company name\n"
                        "  'current_role'             → job title\n"
                        "  'total_experience_years'   → total YOE as a number\n"
                        "  'has_competing_offers'     → 'yes' or 'no'\n"
                        "  'availability'             → e.g. 'immediate', '2_months'\n"
                        "  'location_preference'      → e.g. 'remote_only', 'open_to_hybrid'\n\n"
                        "Call save_candidate_info while ALSO continuing to speak. "
                        "You do not need to say 'Let me note that' — just save it silently."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "field": {
                                "type": "string",
                                "description": "Standardised key name (see conventions above)",
                            },
                            "value": {
                                "type": "string",
                                "description": "The value the candidate stated, normalised to a consistent format",
                            },
                        },
                        "required": ["field", "value"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_github_stats",
                    "description": (
                        "Fetch a candidate's GitHub profile stats (repos, followers, languages). "
                        "Only call this if the candidate mentions their GitHub username."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "username": {"type": "string", "description": "GitHub username"}
                        },
                        "required": ["username"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "end_call",
                    "description": "Call this to end the screening call once you have finished the closing sentence and the candidate has acknowledged it. This will immediately terminate the session.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]
