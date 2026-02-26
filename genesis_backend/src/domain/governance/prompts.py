from jinja2 import Template

ARBITRATION_PROMPT = """
You are a Data Governance Expert. Your task is to decide if a proposed event tracking request conforms to the existing data contract or if it overlaps with existing events.

EXISTING EVENTS:
{% for event in existing_events %}
- CODE: {{ event.code }}, NAME: {{ event.name }}, DESCRIPTION: {{ event.description }}, PROPERTIES: {{ event.properties }}
{% endfor %}

PROPOSED REQUEST:
- NAME: {{ request.name }}
- DESCRIPTION: {{ request.description }}
- PROPERTIES: {{ request.properties }}

INSTRUCTIONS:
1. Compare the proposed request with existing events.
2. If an identical or very similar event exists, recommend REJECT and provide the existing code.
3. If it is new and useful, recommend APPROVE.
4. If it is ambiguous, recommend NEEDS_REVISION.

Respond in structured JSON format with:
- verdict: "APPROVE", "REJECT", or "NEEDS_REVISION"
- score: float (0.0 to 1.0 confidence)
- reasoning: short explanation
- recommended_code: optional string
- risks: list of concrete risk statements
- suggestions: list of actionable edits. Each item should include:
  - title: short suggestion title
  - rationale: why this change helps
  - patch: JSON object containing only fields that should be changed.
    Allowed keys: "name", "description", "properties".
"""

def get_arbitration_prompt(existing_events: list, request_data: dict) -> str:
    template = Template(ARBITRATION_PROMPT)
    return template.render(existing_events=existing_events, request=request_data)
