import json


class LoggerService:

    def log(self, *msg):
        print("[LOG]", *msg)

    def error(self, *msg):
        print("[ERROR]", *msg)

    def latency(self, name: str, ms: float):
        print(f"[LATENCY] {name}: {ms} ms")

    def event(self, name: str, payload: dict):
        print("[EVENT]", name, json.dumps(payload, default=str, ensure_ascii=False))

logger = LoggerService()
