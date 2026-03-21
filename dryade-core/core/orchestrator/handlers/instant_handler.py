"""INSTANT tier handler -- direct LLM response with no orchestration.

Streams a response using a simplified system prompt (no agent roster,
no JSON format). Preserves conversation history for context.

Phase 90: Zero-LLM classifier routes greetings/chitchat here.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from core.extensions.events import (
    ChatEvent,
    emit_complete,
    emit_error,
    emit_thinking,
    emit_token,
)
from core.orchestrator.handlers._utils import (
    INSTANT_SYSTEM_PROMPT,
    _should_emit,
)
from core.orchestrator.handlers.base import OrchestrateHandlerBase

if TYPE_CHECKING:
    from core.orchestrator.router import ExecutionContext

logger = logging.getLogger("dryade.router.orchestrate.instant")

class InstantHandler(OrchestrateHandlerBase):
    """Handle INSTANT tier -- direct LLM response with no orchestration.

    Streams a response using a simplified system prompt (no agent roster,
    no JSON format). Preserves conversation history for context.

    Pitfall 2: Includes conversation history from context.metadata.
    Pitfall 5: Explicitly emits 'complete' event at the end.
    """

    async def handle(
        self,
        message: str,
        context: "ExecutionContext",
        stream: bool = True,
    ) -> AsyncGenerator[ChatEvent, None]:
        """Handle INSTANT tier message.

        Args:
            message: User message (greeting, chitchat, etc.)
            context: Execution context with preferences.
            stream: Whether to stream output token-by-token.

        Yields:
            ChatEvent: token, thinking, complete, or error events.
        """
        from core.orchestrator.thinking import OrchestrationThinkingProvider

        thinking = OrchestrationThinkingProvider()

        # Build messages with conversation history (Pitfall 2)
        history_messages: list[dict] = []
        raw_history = context.metadata.get("history", [])
        if raw_history:
            from core.orchestrator.config import get_orchestration_config

            budget = get_orchestration_config().history_budget_chars
            used = 0
            for msg in reversed(raw_history):
                msg_content = msg.get("content", "")
                msg_len = len(msg_content)
                if used + msg_len > budget:
                    break
                history_messages.insert(0, msg)
                used += msg_len

        # Knowledge context injection (Phase 94.1)
        knowledge_ctx = context.metadata.get("_knowledge_context")
        if knowledge_ctx:
            user_msg = f"RELEVANT KNOWLEDGE:\n{knowledge_ctx}\n\n{message}"
        else:
            user_msg = message

        # Build user message content (multimodal if images attached)
        image_attachments = context.metadata.get("image_attachments")
        if image_attachments and isinstance(image_attachments, list):
            # OpenAI-compatible multimodal content array
            user_content: str | list[dict] = [  # type: ignore[assignment]
                {"type": "text", "text": user_msg},
            ]
            for img in image_attachments[:4]:  # Max 4 images per message
                mime = img.get("mime_type", "image/png")
                b64 = img.get("base64", "")
                if b64:
                    user_content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        }
                    )
        else:
            user_content = user_msg

        messages = [
            {"role": "system", "content": INSTANT_SYSTEM_PROMPT},
            *history_messages,
            {"role": "user", "content": user_content},
        ]

        # Use queue-based streaming bridge (same pattern as COMPLEX handle())
        queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()

        def on_token_cb(token_content: str) -> None:
            queue.put_nowait(emit_token(token_content))

        def on_thinking_cb(reasoning: str) -> None:
            queue.put_nowait(emit_thinking(reasoning))

        streamed_content = ""
        est_tokens = 0

        async def run_instant() -> None:
            nonlocal streamed_content, est_tokens
            try:
                streamed_content, _reasoning, est_tokens = await thinking._stream_llm(
                    messages=messages,
                    on_token=on_token_cb,
                    on_thinking=on_thinking_cb,
                    merge_thinking=False,
                )
                # BUG-003: If model put entire answer in reasoning_content
                # (no content tokens at all), use reasoning as the content.
                # This handles vLLM models that only emit reasoning_content.
                if not streamed_content and _reasoning:
                    streamed_content = _reasoning
                    # Re-emit to the on_token callback so the frontend gets the content
                    if on_token_cb:
                        on_token_cb(_reasoning)
            except Exception as e:
                logger.exception(f"[ORCHESTRATE] INSTANT streaming error: {e}")
                queue.put_nowait(
                    emit_error(
                        f"Error generating response: {type(e).__name__}: {str(e)}",
                        "INSTANT_ERROR",
                    )
                )
            finally:
                queue.put_nowait(None)  # Sentinel

        # Launch streaming as background task
        task = asyncio.create_task(run_instant())

        # Event visibility
        event_visibility = context.metadata.get("event_visibility", "named-steps")

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                # Token events are the final answer -- always pass through.
                # Other events (thinking, error) respect visibility settings.
                if event.type == "token" or _should_emit(event.type, event_visibility):
                    yield event

            await task

        except Exception as e:
            logger.exception(f"[ORCHESTRATE] INSTANT handler error: {e}")
            task.cancel()
            yield emit_error(
                f"Error: {type(e).__name__}: {str(e)}",
                "INSTANT_ERROR",
            )

        # Pitfall 5: MUST emit complete event (frontend depends on it)
        # Don't emit fake fallback content when streaming failed — the error event
        # already informed the frontend. An empty complete just finalizes the stream.
        yield emit_complete(
            response=streamed_content or "",
            usage={
                "prompt_tokens": 0,
                "completion_tokens": est_tokens,
                "total_tokens": est_tokens,
            },
            orchestration_mode="chat",
        )
