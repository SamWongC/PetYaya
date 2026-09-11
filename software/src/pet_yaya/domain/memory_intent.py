"""Intent values shared by the local interpreter and the application."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class MemoryIntent:
    intent: str = "uncertain"
    content: str = ""


def looks_like_memory_request(text):
    return bool(re.search(r"记|記|保存|别忘|別忘|留意|存下来", text))

