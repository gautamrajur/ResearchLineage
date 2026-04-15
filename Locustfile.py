"""
Locust load test for ResearchLineage API
=========================================
Endpoints tested:
  - GET  /analyze/{paper_id}  (cached papers only)
  - POST /chat

Task weights:
  - analyze : 7
  - chat    : 3
"""

import random
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner

CACHED_PAPER_IDS = [
    "1706.03762",
    "1810.04805",
    "1512.03385",
    "1406.1078",
    "1409.0473",
    "2010.11929",
    "1301.3666",
    "1307.0533",
]

CHAT_PAPER_IDS = [
    "1706.03762",
    "1810.04805",
    "1512.03385",
]

CHAT_QUESTIONS = [
    "What problem does this paper solve?",
    "What is the key innovation in this paper?",
    "How does this paper improve on its predecessors?",
    "What are the limitations of this work?",
    "Why was this paper influential?",
]


class ResearchLineageUser(HttpUser):
    wait_time = between(0.5, 1)

    @task(7)
    def analyze(self):
        paper_id = random.choice(CACHED_PAPER_IDS)
        # No name parameter — use full URL so Locust never confuses name with path
        self.client.get(
            f"/analyze/{paper_id}",
            params={"max_depth_tree": 1, "max_children": 2},
        )

    @task(3)
    def chat(self):
        paper_id = random.choice(CHAT_PAPER_IDS)
        question = random.choice(CHAT_QUESTIONS)
        self.client.post(
            "/chat",
            json={
                "paper_id": paper_id,
                "messages": [{"role": "user", "content": question}],
            },
            stream=True,
        )


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    if not isinstance(environment.runner, MasterRunner):
        print("\n" + "-" * 60)
        print("ResearchLineage Load Test")
        print("  Endpoints : /analyze (7), /chat (3)")
        print(f"  Analyze   : {len(CACHED_PAPER_IDS)} cached papers")
        print(f"  Chat      : {len(CHAT_PAPER_IDS)} papers x {len(CHAT_QUESTIONS)} questions")
        print("-" * 60 + "\n")
