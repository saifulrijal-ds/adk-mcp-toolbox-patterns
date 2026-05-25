from google.adk.agents.callback_context import CallbackContext

CORRECTION_SIGNALS = [
    "that's wrong",
    "incorrect",
    "fix the query",
    "wrong query",
    "should be",
    "salah",
    "bukan",
    "harusnya",
    "seharusnya",
    "ubah query",
    "perbaiki",
]


async def memory_extraction_callback(callback_context: CallbackContext) -> None:
    """Auto-extract memory after each agent turn: archive session and detect corrections."""
    await callback_context.add_session_to_memory()

    last_user_text = ""
    for event in reversed(callback_context.session.events):
        if event.author == "user" and event.content and event.content.parts:
            last_user_text = (event.content.parts[0].text or "").lower()
            break

    if any(signal in last_user_text for signal in CORRECTION_SIGNALS):
        callback_context.state["temp:correction_detected"] = True
