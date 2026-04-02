#!/usr/bin/env python3
"""Dental Inventory Agent — CLI entry point.

Usage:
    uv run python main.py                    # uses dental.db (created if missing)
    uv run python main.py --db-url sqlite:///path/to/custom.db

On first run, automatically migrates inventory.json → SQLite.
"""

import argparse
import os

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.exc import SQLAlchemyError

# ANSI color helpers
_GREEN = "\033[32m"
_WHITE = "\033[97m"
_GRAY = "\033[90m"
_RESET = "\033[0m"


def _green(s: str) -> str:
    return f"{_GREEN}{s}{_RESET}"


def _white(s: str) -> str:
    return f"{_WHITE}{s}{_RESET}"


def _gray(s: str) -> str:
    return f"{_GRAY}{s}{_RESET}"


load_dotenv()  # loads .env into os.environ before anything else runs

from app.agent.graph import build_agent  # noqa: E402
from app.db.migrate import load_inventory  # noqa: E402
from app.db.schema import InventoryItemORM, create_tables, make_engine, make_session_factory  # noqa: E402


def _invoke_with_debug(agent: CompiledStateGraph, conversation: list) -> dict:
    """Run the agent with step-by-step debug output.

    Streams each LangGraph node event and prints:
    - LLM tool call decisions (name + arguments)
    - Tool results

    Uses stream_mode="values" so the last yielded value is the complete final
    state — no second invoke needed.
    """
    final_state = None
    # Pre-seed with existing messages so we only print NEW tool calls/results
    seen_message_ids: set = {id(msg) for msg in conversation}

    for state in agent.stream({"messages": conversation}, stream_mode="values"):
        final_state = state
        for msg in state.get("messages", []):
            msg_id = id(msg)
            if msg_id in seen_message_ids:
                continue
            seen_message_ids.add(msg_id)

            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    args_str = ", ".join(f"{k}={v!r}" for k, v in tc["args"].items())
                    print(_gray(f"  [debug] tool_call  → {tc['name']}({args_str})"))
            elif isinstance(msg, ToolMessage):
                content = msg.content
                if len(content) > 400:
                    content = content[:400] + "..."
                indented = content.replace("\n", "\n    ")
                print(_gray(f"  [debug] tool_result ← {msg.name}:\n    {indented}"))

    return final_state


def main() -> None:
    parser = argparse.ArgumentParser(description="Dental Inventory Agent")
    parser.add_argument("--db-url", default="sqlite:///dental.db", help="SQLAlchemy DB URL")
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("DEBUG", "").lower() in ("1", "true"),
        help="Print tool calls, tool results, and LLM reasoning (also set DEBUG=1)",
    )
    args = parser.parse_args()

    # DB setup
    engine = make_engine(args.db_url)
    create_tables(engine)
    Session = make_session_factory(engine)

    # Migrate if inventory is empty
    inv_session = Session()
    if inv_session.query(InventoryItemORM).count() == 0:
        print(_gray("No inventory found. Migrating from case/inventory.json ..."))
        inv_session.close()
        load_inventory(args.db_url)
        inv_session = Session()

    audit_session = Session()

    # Build agent (also loads FAISS index on first call to query_knowledge)
    print(_gray("Loading agent... (first run will download embeddings ~90MB)"))
    agent = build_agent(inv_session, audit_session)

    print(_white("\n" + "=" * 60))
    print(_white("  Dental Inventory Agent"))
    print(_white("  Type your question or command. Press Ctrl+C to exit."))
    print(_white("=" * 60 + "\n"))

    conversation = []

    try:
        while True:
            try:
                user_input = input(_green("You: ")).strip()
            except EOFError:
                break

            if not user_input:
                continue

            conversation.append(HumanMessage(content=user_input))

            try:
                if args.debug:
                    result = _invoke_with_debug(agent, conversation)
                else:
                    result = agent.invoke({"messages": conversation})
            except SQLAlchemyError as e:
                print(
                    _gray(f"\n[DB ERROR] {e}\nThe database operation failed. The conversation state has been reset.\n")
                )
                conversation = []
                continue

            conversation = list(result["messages"])

            # Last message is the agent's response
            last = conversation[-1]
            content = (
                last.content
                if isinstance(last, AIMessage) and last.content
                else "[No response — please try rephrasing your question.]"
            )
            print(_white(f"\nAgent: {content}\n"))

    except KeyboardInterrupt:
        print(_white("\nGoodbye."))
    finally:
        inv_session.close()
        audit_session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
