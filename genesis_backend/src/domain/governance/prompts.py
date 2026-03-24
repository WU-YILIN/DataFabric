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


# ── Module 3: AI 语义字段映射 Prompt ─────────────────────────────────────────
# 关键约束：LLM 只能从 candidates 列表中选择，或返回 UNKNOWN。
# 这是防止幻觉最有效的手段之一（受限选择域）。

MAPPING_PROPOSAL_PROMPT = """
You are a data schema expert at a technology company.
Your ONLY task is to map an unknown raw field to one of the provided standard contract fields.

## Unknown Field
- Field name : {{ unknown_field }}
- Event name : {{ event_name }}
- Sample values: {{ sample_values }}

## Standard Contract Field Candidates (choose ONLY from this list)
{% for c in candidates %}
{{ loop.index }}. field="{{ c.name }}", type="{{ c.field_type }}", description="{{ c.description }}"
{% endfor %}

## Instructions
- Choose the single best match from the candidate list above.
- If none of the candidates match, return "UNKNOWN".
- Do NOT invent field names that are not in the list.
- Return ONLY valid JSON in the following format (no markdown, no explanation):

{
  "matched_field": "<field name from list or UNKNOWN>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence explanation>"
}
"""

def get_mapping_proposal_prompt(
    unknown_field: str,
    event_name: str,
    sample_values: list,
    candidates: list[dict],
) -> str:
    template = Template(MAPPING_PROPOSAL_PROMPT)
    return template.render(
        unknown_field=unknown_field,
        event_name=event_name,
        sample_values=sample_values[:5],  # 最多传 5 个样本值
        candidates=candidates,
    )

