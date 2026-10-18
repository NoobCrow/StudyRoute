"""The small explainer as a model the assistant can use.

It implements the same `complete(system, user)` the cloud clients do, but it is not a chat model:
it is handed the engine's draft answer (`wants_draft`) and rewrites it so that it answers the
question. Its rewrite is then checked twice: by `check_rewrite` (nothing added to the draft,
nothing important dropped) and by the assistant's own guards (numbers, claims, tools). If either
refuses it, the assistant shows the engine's draft instead. The model can make an answer clearer.
It can never make it wrong, because the figures are the engine's and anything else is thrown
away."""

from __future__ import annotations

import json
import logging

from app.ai.explainer.prompt import compact_input, draft_of
from app.ai.explainer.runtime import Explainer
from app.ai.explainer.verify import check_rewrite
from app.ai.guards import GuardFailure
from app.ai.llm import LLMResult

logger = logging.getLogger("studyroute.ai")

# Measured on held-out drafts (docs/AI_EXPLAINER.md): up to this length the model finishes and is
# accepted every time; between 120 and 160 words it finishes 2 times in 14 and is never accepted; it
# then spends 7 to 9 seconds to run out of room. The engine's own draft is shown at once instead.
MAX_DRAFT_WORDS = 120


class LocalExplainerLLM:
    provider = "local"
    wants_draft = True  # the orchestrator appends the engine's draft to the prompt

    def __init__(self, explainer: Explainer) -> None:
        self._explainer = explainer
        self.model = explainer.model_id
        self._last: tuple[str, str] | None = None  # (prompt, reason it was refused)

    def complete(self, *, system: str, user: str) -> LLMResult:
        draft = draft_of(user)
        if not draft:
            raise GuardFailure("NO_DRAFT", "the engine's draft was not in the prompt")
        if len(draft.split()) > MAX_DRAFT_WORDS:
            raise GuardFailure("REWRITE_REJECTED", "DRAFT_TOO_LONG")  # no model time wasted
        key = compact_input(user)
        if self._last is not None and self._last[0] == key:
            # Greedy decoding gives the same answer again: do not spend the time twice.
            raise GuardFailure("REWRITE_REJECTED", self._last[1])
        rewrite = self._explainer.rewrite(key)
        verdict = check_rewrite(draft, rewrite.text) if rewrite.finished else None
        if verdict is None or not verdict.ok:
            reason = "UNFINISHED" if verdict is None else verdict.reason
            self._last = (key, reason)
            logger.info("explainer rewrite refused: %s", reason)
            raise GuardFailure("REWRITE_REJECTED", reason)
        self._last = None
        body = {"reply": rewrite.text, "facts_used": [], "proposed_actions": []}
        return LLMResult(text=json.dumps(body), model=self.model)
