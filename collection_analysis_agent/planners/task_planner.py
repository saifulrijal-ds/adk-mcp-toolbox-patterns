import re
from typing import List, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.llm_request import LlmRequest
from google.adk.planners import BasePlanner
from google.genai import types


class TaskToDoPlanner(BasePlanner):
    """
    A task-list planner that makes the agent explicitly produce
    a numbered TODO list before acting, then ticks off tasks
    as they complete.

    Workflow per turn:
      1. build_planning_instruction → appended to system prompt,
         tells model to emit <TODO> and <DONE> tags.
      2. process_planning_response  → parses those tags, stores
         task state in session, marks thought parts so adk web
         shows them in the thinking block.
    """

    def __init__(
        self,
        thinking_config: Optional[types.ThinkingConfig] = None,
        domain_hint: str = "",
    ):
        self.thinking_config = thinking_config
        self.domain_hint = domain_hint  # e.g. "collection SQL analysis"

    # ------------------------------------------------------------------
    # Step 1: Inject planning instruction into the system prompt
    # ------------------------------------------------------------------
    def build_planning_instruction(
        self,
        readonly_context: ReadonlyContext,
        llm_request: LlmRequest,
    ) -> Optional[str]:

        # Inject thinking config so thoughts show in adk web
        if self.thinking_config and llm_request.config:
            llm_request.config.thinking_config = self.thinking_config

        # Read any tasks already in session state
        state = readonly_context.state
        pending = state.get("todo_pending", [])
        done    = state.get("todo_done", [])

        status_block = ""
        if pending or done:
            status_block = "\n\nCurrent task status:"
            for t in done:
                status_block += f"\n  ✅ {t}"
            for t in pending:
                status_block += f"\n  ⏳ {t}"
            status_block += "\n\nContinue from the first pending task."

        hint = f" for {self.domain_hint}" if self.domain_hint else ""

        return f"""
## Task Planning Protocol{hint}

Before taking any action, output a task list using these tags:

<TODO>
1. First concrete step
2. Second concrete step
3. ...
</TODO>

After completing each step, mark it done:
<DONE>1</DONE>

Rules:
- Emit <TODO> only once per user query (at the start).
- Emit <DONE>N</DONE> after each tool call completes successfully.
- If a step fails, add a <TODO_ADD>new recovery step</TODO_ADD> tag.
- After all tasks are done, write your final answer outside any tags.
- Keep tasks specific and actionable — not "analyze data" but
  "call recall_corrections to check past query fixes for DPD aging".
{status_block}
"""

    # ------------------------------------------------------------------
    # Step 2: Parse tags, update session state, mark thought parts
    # ------------------------------------------------------------------
    def process_planning_response(
        self,
        callback_context: CallbackContext,
        response_parts: List[types.Part],
    ) -> Optional[List[types.Part]]:

        if not response_parts:
            return response_parts

        state = callback_context.state
        pending: list = list(state.get("todo_pending", []))
        done: list    = list(state.get("todo_done", []))

        processed_parts = []

        for part in response_parts:
            if not part.text:
                processed_parts.append(part)
                continue

            text = part.text

            # --- Parse <TODO>...</TODO> (initial task list) ---
            todo_match = re.search(
                r"<TODO>(.*?)</TODO>", text, re.DOTALL | re.IGNORECASE
            )
            if todo_match and not pending and not done:
                raw_tasks = todo_match.group(1).strip()
                tasks = [
                    re.sub(r"^\d+\.\s*", "", line).strip()
                    for line in raw_tasks.splitlines()
                    if line.strip()
                ]
                pending = tasks
                state["todo_pending"] = pending
                state["todo_done"]    = done

            # --- Parse <DONE>N</DONE> ---
            done_matches = re.findall(
                r"<DONE>(\d+)</DONE>", text, re.IGNORECASE
            )
            for idx_str in done_matches:
                idx = int(idx_str) - 1  # convert 1-based to 0-based
                if 0 <= idx < len(pending):
                    completed = pending.pop(idx)
                    done.append(completed)
                    state["todo_pending"] = pending
                    state["todo_done"]    = done

            # --- Parse <TODO_ADD>new task</TODO_ADD> ---
            add_matches = re.findall(
                r"<TODO_ADD>(.*?)</TODO_ADD>", text, re.IGNORECASE
            )
            for new_task in add_matches:
                pending.append(new_task.strip())
                state["todo_pending"] = pending

            # Mark planning/tag text as a thought so adk web
            # shows it in the collapsible thinking block
            has_tags = bool(
                re.search(
                    r"<TODO>|</TODO>|<DONE>|<TODO_ADD>",
                    text,
                    re.IGNORECASE,
                )
            )
            if has_tags:
                processed_parts.append(
                    types.Part(text=text, thought=True)
                )
            else:
                processed_parts.append(part)

        return processed_parts
