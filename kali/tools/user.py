"""AskUserQuestion - interactive multiple-choice questions.

ExitPlanMode moved to kali/tools/plan.py (it pairs with EnterPlanMode there);
it is re-exported below for import compatibility.
"""
from __future__ import annotations

from .base import Tool, ToolResult, ToolContext, _s
from .plan import ExitPlanMode  # noqa: F401  (re-export for compatibility)


class AskUserQuestion(Tool):
    name = "AskUserQuestion"
    # Verbatim from the Sonnet 4.6 CLI leak (spec section 2.1).
    description = """Use this tool only when you are blocked on a decision that is genuinely the user's to make: one you cannot resolve from the request, the code, or sensible defaults.

Usage notes:
- Users will always be able to select "Other" to provide custom text input
- Use multiSelect: true to allow multiple answers to be selected for a question
- If you recommend a specific option, make that the first option in the list and add "(Recommended)" at the end of the label

Plan mode note: To switch into plan mode, use EnterPlanMode (not this tool). Once in plan mode, use this tool to clarify requirements or choose between approaches BEFORE finalizing your plan. Do NOT use this tool to ask "Is my plan ready?", "Should I proceed?", or otherwise reference "the plan" in questions - the user cannot see the plan until you call ExitPlanMode for approval.

The user may see only the question dialog: tool results and text you wrote earlier in this turn may not be on their screen while it is open. Make each question stand on its own: if it depends on something you found, say so briefly, and name the items you are asking about in the question itself.

Preview feature:
Use the optional `preview` field on options when presenting concrete artifacts that users need to visually compare:
- ASCII mockups of UI layouts or components
- Code snippets showing different implementations
- Diagram variations
- Configuration examples

Preview content is rendered as markdown in a monospace box. Multi-line text with newlines is supported. When any option has a preview, the UI switches to a side-by-side layout with a vertical option list on the left and preview on the right. Do not use previews for simple preference questions where labels and descriptions suffice. Note: previews are only supported for single-select questions (not multiSelect)."""
    # Verbatim schema (header max 12 chars; options carry label/description/preview).
    schema = _s(
        {
            "questions": {
                "description": "Questions to ask the user (1-4 questions)",
                "minItems": 1,
                "maxItems": 4,
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"description": "The complete question to ask the user. Should be clear, specific, and end with a question mark. Example: \"Which library should we use for date formatting?\" If multiSelect is true, phrase it accordingly, e.g. \"Which features do you want to enable?\"", "type": "string"},
                        "header": {"description": "Very short label displayed as a chip/tag (max 12 chars). Examples: \"Auth method\", \"Library\", \"Approach\".", "type": "string"},
                        "options": {
                            "description": "The available choices for this question. Must have 2-4 options. Each option should be a distinct, mutually exclusive choice (unless multiSelect is enabled). There should be no 'Other' option, that will be provided automatically.",
                            "minItems": 2,
                            "maxItems": 4,
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"description": "The display text for this option that the user will see and select. Should be concise (1-5 words) and clearly describe the choice.", "type": "string"},
                                    "description": {"description": "Explanation of what this option means or what will happen if chosen. Useful for providing context about trade-offs or implications.", "type": "string"},
                                    "preview": {"description": "Optional preview content rendered when this option is focused. Use for mockups, code snippets, or visual comparisons that help users compare options. See the tool description for the expected content format.", "type": "string"},
                                },
                                "required": ["label", "description"],
                                "additionalProperties": False,
                            },
                        },
                        "multiSelect": {"description": "Set to true to allow the user to select multiple options instead of just one. Use when choices are not mutually exclusive.", "default": False, "type": "boolean"},
                    },
                    "required": ["question", "header", "options", "multiSelect"],
                    "additionalProperties": False,
                },
            },
            "answers": {"description": "User answers collected by the permission component", "type": "object", "propertyNames": {"type": "string"}, "additionalProperties": {"type": "string"}},
            "annotations": {
                "description": "Optional per-question annotations from the user (e.g., notes on preview selections). Keyed by question text.",
                "type": "object",
                "propertyNames": {"type": "string"},
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "preview": {"description": "The preview content of the selected option, if the question used previews.", "type": "string"},
                        "notes": {"description": "Free-text notes the user added to their selection.", "type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "metadata": {
                "description": "Optional metadata for tracking and analytics purposes. Not displayed to user.",
                "type": "object",
                "properties": {
                    "source": {"description": "Optional identifier for the source of this question (e.g., \"remember\" for /remember command). Used for analytics tracking.", "type": "string"},
                },
                "additionalProperties": False,
            },
        },
        required=["questions"],
    )

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        answers = await ctx.agent.ask_user_questions(args.get("questions", []))
        if answers is None:
            return ToolResult("User declined to answer (interrupted).", error=True)
        return ToolResult(json_dumps(answers))


def json_dumps(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
