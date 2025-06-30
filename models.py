import re
from datetime import datetime
from typing import List
class IPTVChannel:
    def __init__(self, extinf_line: str, url: str):
        self.extinf_line = extinf_line.strip()
        self.url = url.strip()
        self.name = self._extract_name()
        self.is_working = False
        self.response_time = 0
        self.error_message = ""
        self.check_time = None
    def _extract_name(self) -> str:
        match = re.search(r',([^,]+)$', self.extinf_line)
        if match:
            return match.group(1).strip()
        return "Unknown Channel"
    def __str__(self):
        return f"{self.name} - {'✓' if self.is_working else '✗'}"