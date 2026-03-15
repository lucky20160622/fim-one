"""Built-in skill templates.

These are hardcoded skill definitions that serve as starting points for users
creating new skills.  They are NOT stored in the database -- the API returns
them from memory and allows creating a real ``Skill`` row from any template.
"""

from __future__ import annotations

import copy
from typing import Any

# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

_SUMMARIZATION: dict[str, Any] = {
    "id": "summarization",
    "name": "Summarization",
    "description": "Summarize text documents, articles, or conversations",
    "icon": "FileText",
    "category": "text",
    "blueprint": {
        "content": (
            "## Summarization Skill\n\n"
            "### Purpose\n"
            "Produce a concise, accurate summary of the provided text while "
            "preserving the key information and original intent.\n\n"
            "### Instructions\n"
            "1. Read the provided text carefully from start to finish.\n"
            "2. Identify the main topic, key arguments, and supporting details.\n"
            "3. Determine the appropriate summary length:\n"
            "   - Short text (< 500 words): 2-3 sentence summary\n"
            "   - Medium text (500-2000 words): 1 paragraph summary\n"
            "   - Long text (> 2000 words): multi-paragraph summary with section headings\n"
            "4. Write the summary in clear, neutral language.\n"
            "5. Preserve any critical numbers, dates, or proper nouns.\n"
            "6. Do NOT introduce information not present in the original text.\n\n"
            "### Output Format\n"
            "```\n"
            "**Summary**\n\n"
            "[Your concise summary here]\n\n"
            "**Key Points**\n"
            "- Point 1\n"
            "- Point 2\n"
            "- Point 3\n"
            "```\n\n"
            "### Quality Checklist\n"
            "- [ ] Captures the main idea accurately\n"
            "- [ ] No hallucinated or fabricated details\n"
            "- [ ] Appropriate length for the source material\n"
            "- [ ] Neutral tone maintained"
        ),
        "description": "Summarize documents, articles, or conversation transcripts into concise briefs",
    },
}

_TRANSLATION: dict[str, Any] = {
    "id": "translation",
    "name": "Translation",
    "description": "Translate text between languages with context awareness",
    "icon": "Languages",
    "category": "text",
    "blueprint": {
        "content": (
            "## Translation Skill\n\n"
            "### Purpose\n"
            "Translate text accurately between languages while preserving "
            "meaning, tone, and cultural context.\n\n"
            "### Instructions\n"
            "1. **Detect the source language** if not explicitly specified.\n"
            "2. **Identify the target language** from the user's request.\n"
            "3. Translate the content following these rules:\n"
            "   - Preserve the original meaning and intent\n"
            "   - Maintain the same register (formal/informal/technical)\n"
            "   - Adapt idioms and cultural references appropriately\n"
            "   - Keep proper nouns, brand names, and technical terms as-is "
            "unless a well-known localized form exists\n"
            "   - Preserve formatting (markdown, lists, headings)\n"
            "4. If the text contains ambiguity, choose the most likely "
            "interpretation and note the alternative.\n\n"
            "### Language Detection\n"
            "When the source language is not specified:\n"
            "- Analyze character set, grammar patterns, and vocabulary\n"
            "- State the detected language before translating\n"
            "- If confidence is low, ask the user to confirm\n\n"
            "### Output Format\n"
            "```\n"
            "**Source language**: [detected or specified]\n"
            "**Target language**: [requested]\n\n"
            "---\n\n"
            "[Translated text here]\n"
            "```\n\n"
            "### Special Cases\n"
            "- **Technical documents**: maintain terminology consistency throughout\n"
            "- **Poetry/creative text**: prioritize conveying emotion and style "
            "over literal translation\n"
            "- **Legal/medical text**: flag that professional review is recommended"
        ),
        "description": "Translate text between languages with automatic language detection and context-aware adaptation",
    },
}

_DATA_EXTRACTION: dict[str, Any] = {
    "id": "data-extraction",
    "name": "Data Extraction",
    "description": "Extract structured JSON data from unstructured text",
    "icon": "Database",
    "category": "data",
    "blueprint": {
        "content": (
            "## Data Extraction Skill\n\n"
            "### Purpose\n"
            "Extract structured data from unstructured text and return it in "
            "a clean, machine-readable JSON format.\n\n"
            "### Instructions\n"
            "1. Analyze the input text to identify extractable entities.\n"
            "2. Determine the appropriate schema based on the content type:\n"
            "   - People: name, email, phone, role, organization\n"
            "   - Dates/Events: date, time, location, description\n"
            "   - Products: name, price, SKU, category, attributes\n"
            "   - Addresses: street, city, state, zip, country\n"
            "3. Extract all matching entities from the text.\n"
            "4. Normalize values (e.g., dates to ISO 8601, phones to E.164).\n"
            "5. Return valid JSON with consistent key naming (snake_case).\n\n"
            "### Output Format\n"
            "Always return a JSON object with a `results` array:\n"
            "```json\n"
            "{\n"
            '  "entity_type": "person",\n'
            '  "confidence": 0.95,\n'
            '  "results": [\n'
            "    {\n"
            '      "name": "Jane Doe",\n'
            '      "email": "jane@example.com",\n'
            '      "phone": "+1-555-0100",\n'
            '      "role": "Engineering Manager",\n'
            '      "organization": "Acme Corp"\n'
            "    }\n"
            "  ],\n"
            '  "unmatched_fragments": []\n'
            "}\n"
            "```\n\n"
            "### Rules\n"
            "- Use `null` for fields that cannot be determined\n"
            "- Include a `confidence` score (0.0-1.0) for the overall extraction\n"
            "- List any text fragments that could not be categorized in "
            "`unmatched_fragments`\n"
            "- Validate JSON output before returning\n"
            "- Never invent data that is not present in the source text"
        ),
        "description": "Extract structured JSON from unstructured text with automatic entity detection and schema inference",
    },
}

_EMAIL_DRAFTING: dict[str, Any] = {
    "id": "email-drafting",
    "name": "Email Drafting",
    "description": "Draft professional emails with appropriate tone and format",
    "icon": "Mail",
    "category": "writing",
    "blueprint": {
        "content": (
            "## Email Drafting Skill\n\n"
            "### Purpose\n"
            "Draft clear, professional emails tailored to the audience and "
            "context provided.\n\n"
            "### Instructions\n"
            "1. **Determine the email type** from the user's request:\n"
            "   - Business proposal / pitch\n"
            "   - Follow-up / reminder\n"
            "   - Request / inquiry\n"
            "   - Thank you / acknowledgment\n"
            "   - Apology / issue resolution\n"
            "   - Internal announcement / update\n"
            "2. **Select the appropriate tone**:\n"
            "   - Formal: executive communication, external partners, legal\n"
            "   - Professional: standard business correspondence\n"
            "   - Friendly: team updates, peer communication\n"
            "   - Urgent: time-sensitive matters (concise, action-oriented)\n"
            "3. **Structure the email**:\n"
            "   - Subject line: concise, actionable, under 60 characters\n"
            "   - Opening: context or greeting appropriate to relationship\n"
            "   - Body: key message with clear paragraphs (max 3-4)\n"
            "   - Call to action: specific next step with deadline if applicable\n"
            "   - Closing: appropriate sign-off for the tone\n\n"
            "### Output Format\n"
            "```\n"
            "**Subject**: [Subject line]\n\n"
            "[Greeting],\n\n"
            "[Body paragraph 1 - context/purpose]\n\n"
            "[Body paragraph 2 - details]\n\n"
            "[Call to action]\n\n"
            "[Closing],\n"
            "[Signature placeholder]\n"
            "```\n\n"
            "### Guidelines\n"
            "- Keep total length under 200 words unless complexity requires more\n"
            "- Use bullet points for lists of 3+ items\n"
            "- Avoid jargon unless writing to domain experts\n"
            "- Include placeholders like `[Company Name]` for unknown details\n"
            "- Flag if the request seems emotionally charged and suggest a cooling-off review"
        ),
        "description": "Draft professional emails with context-appropriate tone, structure, and clear calls to action",
    },
}

_CODE_EXPLANATION: dict[str, Any] = {
    "id": "code-explanation",
    "name": "Code Explanation",
    "description": "Explain code step by step with clear annotations",
    "icon": "Code",
    "category": "code",
    "blueprint": {
        "content": (
            "## Code Explanation Skill\n\n"
            "### Purpose\n"
            "Explain code clearly and thoroughly, making it accessible to "
            "developers of varying skill levels.\n\n"
            "### Instructions\n"
            "1. **Identify the language and framework** used in the code.\n"
            "2. **Provide a high-level overview** (1-2 sentences) of what "
            "the code does.\n"
            "3. **Walk through the code step by step**:\n"
            "   - Explain each logical section or function\n"
            "   - Describe the purpose of key variables and data structures\n"
            "   - Note any design patterns being used\n"
            "   - Highlight non-obvious behavior or edge cases\n"
            "4. **Note potential issues** (bugs, performance concerns, "
            "security vulnerabilities) if any.\n"
            "5. **Suggest improvements** if relevant.\n\n"
            "### Output Format\n"
            "```\n"
            "### Overview\n"
            "[Brief description of what the code does]\n\n"
            "### Language & Dependencies\n"
            "- Language: [e.g., Python 3.11]\n"
            "- Key libraries: [e.g., asyncio, SQLAlchemy]\n\n"
            "### Step-by-Step Breakdown\n\n"
            "**Lines 1-5: [Section name]**\n"
            "[Explanation of this section]\n\n"
            "**Lines 6-12: [Section name]**\n"
            "[Explanation of this section]\n\n"
            "### Key Concepts\n"
            "- [Concept 1]: [Brief explanation]\n"
            "- [Concept 2]: [Brief explanation]\n\n"
            "### Potential Issues\n"
            "- [Issue description and recommended fix]\n"
            "```\n\n"
            "### Adaptation Rules\n"
            "- For beginners: explain basic constructs (loops, conditionals)\n"
            "- For intermediate: focus on patterns and architecture\n"
            "- For advanced: focus on performance, edge cases, and trade-offs\n"
            "- Default to intermediate level unless specified"
        ),
        "description": "Explain code step by step with clear annotations, pattern identification, and improvement suggestions",
    },
}

_SENTIMENT_ANALYSIS: dict[str, Any] = {
    "id": "sentiment-analysis",
    "name": "Sentiment Analysis",
    "description": "Analyze text sentiment with detailed scoring and reasoning",
    "icon": "BarChart3",
    "category": "ai",
    "blueprint": {
        "content": (
            "## Sentiment Analysis Skill\n\n"
            "### Purpose\n"
            "Analyze the sentiment of text and provide a structured assessment "
            "with scores, labels, and supporting evidence.\n\n"
            "### Instructions\n"
            "1. Read the input text carefully.\n"
            "2. Assess the overall sentiment on a 5-point scale.\n"
            "3. Identify sentiment-bearing phrases and classify each.\n"
            "4. Detect the emotional undertones (anger, joy, sadness, etc.).\n"
            "5. Consider context, sarcasm, and cultural nuances.\n\n"
            "### Scoring Rubric\n"
            "| Score | Label        | Description                              |\n"
            "|-------|--------------|------------------------------------------|\n"
            "| 1.0   | Very Negative| Strong dissatisfaction, anger, hostility  |\n"
            "| 2.0   | Negative     | Dissatisfaction, disappointment, concern  |\n"
            "| 3.0   | Neutral      | Factual, balanced, no strong emotion      |\n"
            "| 4.0   | Positive     | Satisfaction, approval, enthusiasm        |\n"
            "| 5.0   | Very Positive| Strong approval, excitement, delight      |\n\n"
            "Half-point scores (e.g., 3.5) are allowed for mixed sentiment.\n\n"
            "### Output Format\n"
            "```json\n"
            "{\n"
            '  "overall_score": 3.5,\n'
            '  "overall_label": "Slightly Positive",\n'
            '  "confidence": 0.85,\n'
            '  "emotions": ["satisfaction", "mild_concern"],\n'
            '  "evidence": [\n'
            "    {\n"
            '      "phrase": "really enjoyed the experience",\n'
            '      "sentiment": "positive",\n'
            '      "score": 4.5\n'
            "    },\n"
            "    {\n"
            '      "phrase": "but the wait was too long",\n'
            '      "sentiment": "negative",\n'
            '      "score": 2.0\n'
            "    }\n"
            "  ],\n"
            '  "summary": "The text expresses overall satisfaction with a minor complaint about wait times."\n'
            "}\n"
            "```\n\n"
            "### Special Considerations\n"
            "- **Sarcasm**: flag when detected, score based on intended meaning\n"
            "- **Mixed sentiment**: report the dominant sentiment but note conflicts\n"
            "- **Multi-topic text**: provide per-topic breakdown if topics differ in sentiment\n"
            "- **Cultural context**: note if sentiment interpretation may vary across cultures"
        ),
        "description": "Analyze text sentiment with a 5-point scoring rubric, emotion detection, and evidence-based reasoning",
    },
}

# ---------------------------------------------------------------------------
# Public list & index
# ---------------------------------------------------------------------------

SKILL_TEMPLATES: list[dict[str, Any]] = [
    _SUMMARIZATION,
    _TRANSLATION,
    _DATA_EXTRACTION,
    _EMAIL_DRAFTING,
    _CODE_EXPLANATION,
    _SENTIMENT_ANALYSIS,
]

_TEMPLATES_BY_ID: dict[str, dict[str, Any]] = {t["id"]: t for t in SKILL_TEMPLATES}


def list_templates() -> list[dict[str, Any]]:
    """Return deep copies of all built-in skill templates."""
    return copy.deepcopy(SKILL_TEMPLATES)


def get_template(template_id: str) -> dict[str, Any] | None:
    """Return a deep copy of the template with the given ID, or None."""
    tpl = _TEMPLATES_BY_ID.get(template_id)
    if tpl is None:
        return None
    return copy.deepcopy(tpl)
