"""
locustfile.py — Locust load test for the classifier and generator services.
Run with:
  locust -f locustfile.py --host http://<host>:8001 --users 20 --spawn-rate 5 --run-time 60s --headless

Simulates peak Zulip load: ~17 req/s across 200 users.
"""

from locust import HttpUser, task, between
import random

TEST_MESSAGES = [
    "yo can u just fix the bug already its been 3 days lol",
    "i cant believe this lol, the whole thing is broken",
    "please review my pr when u get a chance",
    "Fix this. NOW.",
    "Could you help me understand the deployment pipeline?",
    "we need to talk about the deadline it's tomorrow and nothing works",
    "great work on the presentation everyone!!",
    "the server is down again, classic",
    "Can someone please update the documentation?",
    "meeting starts in 5, where r u??",
]


class ClassifierUser(HttpUser):
    """Simulates users hitting the classifier endpoint."""
    wait_time = between(0.5, 2.0)  # ~17 req/s at 200 users with 2s avg wait

    @task
    def predict_tone(self):
        payload = {
            "message_id": f"msg_{random.randint(1000, 9999)}",
            "text": random.choice(TEST_MESSAGES),
            "message_type": random.choice(["stream", "direct"]),
        }
        with self.client.post("/predict", json=payload, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"Got status {resp.status_code}")
            elif resp.elapsed.total_seconds() > 0.8:
                resp.failure(f"p95 latency target breached: {resp.elapsed.total_seconds()*1000:.0f}ms")
