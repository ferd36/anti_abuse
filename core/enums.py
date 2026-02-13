"""
Enumerations for the anti-abuse system.
"""

from enum import Enum

from core.constants import (
    GENERATION_PATTERN_CLEAN,
    VALID_ACCOUNT_TIERS,
    VALID_COUNTRIES,
    VALID_LANGUAGES,
    VALID_USER_TYPES,
)

__all__ = [
    "GENERATION_PATTERN_CLEAN",
    "InteractionType",
    "IPType",
    "VALID_ACCOUNT_TIERS",
    "VALID_COUNTRIES",
    "VALID_LANGUAGES",
    "VALID_USER_TYPES",
]


class IPType(Enum):
    RESIDENTIAL = "residential"
    HOSTING = "hosting"


class InteractionType(Enum):
    ACCOUNT_CREATION = "account_creation"
    LOGIN = "login"
    CHANGE_PASSWORD = "change_password"
    CHANGE_PROFILE = "change_profile"
    CHANGE_NAME = "change_name"
    UPDATE_HEADLINE = "update_headline"  # job title change, e.g. when changing jobs
    UPDATE_SUMMARY = "update_summary"    # profile summary/bio update
    CHANGE_LAST_NAME = "change_last_name"  # marital name change
    MESSAGE_USER = "message_user"
    VIEW_USER_PAGE = "view_user_page"
    SEARCH_CANDIDATES = "search_candidates"  # recruiter candidate search
    LIKE = "like"
    REACT = "react"
    UPLOAD_ADDRESS_BOOK = "upload_address_book"
    DOWNLOAD_ADDRESS_BOOK = "download_address_book"
    CLOSE_ACCOUNT = "close_account"
    CONNECT_WITH_USER = "connect_with_user"
    # Credibility
    ENDORSE_SKILL = "endorse_skill"           # target_user_id, skill_id in metadata
    GIVE_RECOMMENDATION = "give_recommendation"  # target_user_id
    CREATE_JOB_POSTING = "create_job_posting"   # no target; job_id in metadata
    APPLY_TO_JOB = "apply_to_job"               # job_id in metadata; target_user_id optional
    VIEW_JOB = "view_job"                       # job_id in metadata
    SEND_CONNECTION_REQUEST = "send_connection_request"  # same as CONNECT_WITH_USER semantically
    ACCEPT_CONNECTION_REQUEST = "accept_connection_request"  # user_id accepts target_user_id's request
    JOIN_GROUP = "join_group"                   # group_id in metadata
    LEAVE_GROUP = "leave_group"                 # group_id in metadata
    POST_IN_GROUP = "post_in_group"             # group_id in metadata; optional target for reply
    AD_VIEW = "ad_view"                         # ad_id in metadata
    AD_CLICK = "ad_click"                       # ad_id in metadata
    # Auth anomaly
    SESSION_LOGIN = "session_login"             # login via stolen session token
    PHISHING_LOGIN = "phishing_login"           # credential capture event
