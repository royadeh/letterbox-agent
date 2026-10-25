"""The Letterbox graph: extract -> verify -> explain -> options -> reply.

Any step that cannot give a trustworthy answer takes the "I'm not sure" path.
The technical reason goes to the log with the run's reference; the reader
sees only "I'm not sure, check with the sender" and that reference.
"""

import logging
import uuid
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict

from letterbox.answers import NotSure
from letterbox.explain import Explanation, explain
from letterbox.extract import extract
from letterbox.llm import LLMClient
from letterbox.options import Options, list_options
from letterbox.placeholders import CHECK_WITH_SENDER_FA
from letterbox.reply import Reply, draft_reply
from letterbox.schema import LetterFacts
from letterbox.verify import VerifiedFacts, verify

logger = logging.getLogger("letterbox")

READER_NOT_SURE = "I'm not sure, check with the sender"
READER_NOT_SURE_FA = CHECK_WITH_SENDER_FA
NO_OPTIONS = "No actions were found in the letter."
NO_OPTIONS_FA = "در این نامه اقدامی پیدا نشد."
DISCLAIMER = "General information only, not legal or tax advice."
DISCLAIMER_FA = "این فقط اطلاعات عمومی است، نه مشاوره حقوقی یا مالیاتی."

Route = Literal["continue", "not_sure"]


class Answer(BaseModel):
    """What the reader sees. Empty sections are left out of the text."""

    model_config = ConfigDict(frozen=True)

    explanation_en: str
    explanation_fa: str
    options_en: str = ""
    options_fa: str = ""
    reply_en: str = ""
    reply_fa: str = ""
    disclaimer_en: str = DISCLAIMER
    disclaimer_fa: str = DISCLAIMER_FA

    def text(self) -> str:
        sections = [
            ("Explanation", self.explanation_en),
            ("توضیح", self.explanation_fa),
            ("Your options", self.options_en),
            ("گزینه‌های شما", self.options_fa),
            ("Reply draft (check it before you send it)", self.reply_en),
            ("توضیح پیش‌نویس پاسخ", self.reply_fa),
        ]
        parts = [f"{title}\n{body}" for title, body in sections if body]
        return "\n\n".join([*parts, self.disclaimer_en, self.disclaimer_fa]) + "\n"


class State(TypedDict, total=False):
    letter: str
    run_id: str
    facts: LetterFacts
    verified: VerifiedFacts
    explanation: Explanation
    option_list: Options | None  # None: the options step was not sure
    reply_draft: Reply | None  # None: the reply step was not sure
    failed: bool
    answer: Answer


def new_run_id() -> str:
    return uuid.uuid4().hex[:8]


def run(letter: str, client: LLMClient, run_id: str | None = None) -> Answer:
    final = build_graph(client).invoke({"letter": letter, "run_id": run_id or new_run_id()})
    return final["answer"]


def build_graph(client: LLMClient) -> CompiledStateGraph:
    def extract_node(state: State) -> State:
        return _extract(state, client)

    def explain_node(state: State) -> State:
        return _explain(state, client)

    def options_node(state: State) -> State:
        return _options(state, client)

    def reply_node(state: State) -> State:
        return _reply(state, client)

    builder = StateGraph(State)
    builder.add_node("extract", extract_node)
    builder.add_node("verify", _verify)
    builder.add_node("explain", explain_node)
    builder.add_node("options", options_node)
    builder.add_node("reply", reply_node)
    builder.add_node("finish", _finish)
    builder.add_node("not_sure", _not_sure)
    builder.add_edge(START, "extract")
    builder.add_conditional_edges("extract", _route, {"continue": "verify", "not_sure": "not_sure"})
    builder.add_conditional_edges("verify", _route, {"continue": "explain", "not_sure": "not_sure"})
    builder.add_conditional_edges("explain", _route, {"continue": "options", "not_sure": "not_sure"})
    builder.add_edge("options", "reply")
    builder.add_edge("reply", "finish")
    builder.add_edge("finish", END)
    builder.add_edge("not_sure", END)
    return builder.compile()


def _route(state: State) -> Route:
    return "not_sure" if state.get("failed") else "continue"


def _extract(state: State, client: LLMClient) -> State:
    result = extract(state["letter"], client)
    if isinstance(result, NotSure):
        return _fail(state, "extract", result.reason)
    return {"facts": result}


def _verify(state: State) -> State:
    verified = verify(state["facts"], state["letter"])
    if verified.dropped:
        logger.info("run %s: verify dropped %d unsupported facts", state["run_id"], len(verified.dropped))
    if not verified.facts:
        return _fail(state, "verify", "No facts could be checked against the letter.")
    return {"verified": verified}


def _explain(state: State, client: LLMClient) -> State:
    result = explain(state["verified"], client)
    if isinstance(result, NotSure):
        return _fail(state, "explain", result.reason)
    return {"explanation": result}


def _options(state: State, client: LLMClient) -> State:
    result = list_options(state["verified"], client)
    if isinstance(result, NotSure):
        _log_not_sure(state, "options", result.reason)
        return {"option_list": None}
    return {"option_list": result}


def _reply(state: State, client: LLMClient) -> State:
    result = draft_reply(state["verified"], client)
    if isinstance(result, NotSure):
        _log_not_sure(state, "reply", result.reason)
        return {"reply_draft": None}
    return {"reply_draft": result}


def _fail(state: State, step: str, reason: str) -> State:
    _log_not_sure(state, step, reason)
    return {"failed": True}


def _log_not_sure(state: State, step: str, reason: str) -> None:
    logger.warning("run %s: %s step is not sure: %s", state["run_id"], step, reason)


def _not_sure_lines(run_id: str) -> tuple[str, str]:
    return f"{READER_NOT_SURE} (Reference: {run_id})", f"{READER_NOT_SURE_FA} (Reference: {run_id})"


def _not_sure(state: State) -> State:
    english, farsi = _not_sure_lines(state["run_id"])
    return {"answer": Answer(explanation_en=english, explanation_fa=farsi)}


def _finish(state: State) -> State:
    options_en, options_fa = _options_text(state.get("option_list"), state["run_id"])
    reply_en, reply_fa = _reply_text(state.get("reply_draft"), state["run_id"])
    explanation = state["explanation"]
    answer = Answer(
        explanation_en=explanation.english,
        explanation_fa=explanation.farsi,
        options_en=options_en,
        options_fa=options_fa,
        reply_en=reply_en,
        reply_fa=reply_fa,
    )
    return {"answer": answer}


def _options_text(options: Options | None, run_id: str) -> tuple[str, str]:
    if options is None:
        return _not_sure_lines(run_id)
    if not options.items:
        return NO_OPTIONS, NO_OPTIONS_FA
    return options.english, options.farsi


def _reply_text(reply: Reply | None, run_id: str) -> tuple[str, str]:
    if reply is None:
        return _not_sure_lines(run_id)
    return reply.english, reply.farsi_explanation
