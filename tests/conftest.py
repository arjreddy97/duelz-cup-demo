import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import sandbox  # noqa: E402


@pytest.fixture
def ws():
    path = sandbox.new_workspace("demo-test-")
    yield path
    sandbox.drop_workspace(path)


class ScriptedModel:
    """Replies with a fixed list of texts and records what it was sent."""

    def __init__(self, replies, prompt=100, cached=0, output=10):
        self.replies = list(replies)
        self.sent = []
        self.usage = (prompt, cached, output)

    async def generate(self, contents, system):
        from app.gemini import Usage
        self.sent.append([dict(c) for c in contents])
        text = self.replies.pop(0) if self.replies else '{"action": "finish"}'
        if isinstance(text, Exception):
            raise text
        size = sum(len(c["text"]) for c in contents)
        return text, Usage(prompt=self.usage[0] + size, cached=self.usage[1], output=self.usage[2])


@pytest.fixture
def scripted():
    return ScriptedModel
