import json

def format_sse_event(data: dict, event_id: str | None = None) -> str:
    """Format data as SSE event."""
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {data.get('type', 'message')}")
    json_data = json.dumps(data, default=str)
    for line in json_data.split("\n"):
        lines.append(f"data: {line}")
    lines.append("")
    return "\n".join(lines) + "\n"


