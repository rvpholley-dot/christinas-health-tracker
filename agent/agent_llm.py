"""Claude tool-use agent (Phase 2).

Will run a claude-haiku-4-5 messages-API loop with tools (log_entry, get_log,
get_totals, update_entry, delete_entry, get_schedule, remember), conversation
memory from the conversations table, and the christina.md profile injected
into the system prompt.

Phase 0 placeholder so imports and module layout are stable.
"""


def handle_message(config: dict, chat_id, text: str) -> str:
    raise NotImplementedError("Phase 2: Claude agent loop not built yet")
