from dataclasses import dataclass, field
from enum import Enum


class ConversationStep(str, Enum):
    START = "START"
    WAITING_MOBILE = "WAITING_MOBILE"
    WAITING_NAME = "WAITING_NAME"
    WAITING_LANGUAGE = "WAITING_LANGUAGE"
    WAITING_AREA = "WAITING_AREA"
    MAIN_MENU = "MAIN_MENU"
    WORKER_CATEGORY = "WORKER_CATEGORY"
    WORKER_EXPERIENCE = "WORKER_EXPERIENCE"
    WORKER_AVAILABILITY = "WORKER_AVAILABILITY"
    WORKER_LOCATION = "WORKER_LOCATION"


@dataclass
class ConversationSession:
    step: ConversationStep = ConversationStep.START
    data: dict = field(default_factory=dict)
