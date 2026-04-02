#!/usr/bin/env python3
"""Dental Inventory Agent — CLI entry point.

Usage:
    uv run python main.py                    # uses dental.db (created if missing)
    uv run python main.py --db-url sqlite:///path/to/custom.db

On first run, automatically migrates inventory.json → SQLite.
"""

import argparse

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()  # loads .env into os.environ before anything else runs

from app.agent.graph import build_agent
from app.db.migrate import load_inventory
from app.db.schema import InventoryItemORM, create_tables, make_engine, make_session_factory


def main():
    parser = argparse.ArgumentParser(description="Dental Inventory Agent")
    parser.add_argument("--db-url", default="sqlite:///dental.db", help="SQLAlchemy DB URL")
    args = parser.parse_args()

    # DB setup
    engine = make_engine(args.db_url)
    create_tables(engine)
    Session = make_session_factory(engine)

    # Migrate if inventory is empty
    inv_session = Session()
    if inv_session.query(InventoryItemORM).count() == 0:
        print("No inventory found. Migrating from case/inventory.json ...")
        inv_session.close()
        load_inventory(args.db_url)
        inv_session = Session()

    audit_session = Session()

    # Build agent (also loads FAISS index on first call to query_knowledge)
    print("Loading agent... (first run will download embeddings ~90MB)")
    agent = build_agent(inv_session, audit_session)

    print("\n" + "=" * 60)
    print("  Dental Inventory Agent")
    print("  Type your question or command. Press Ctrl+C to exit.")
    print("=" * 60 + "\n")

    conversation = []

    try:
        while True:
            try:
                user_input = input("You: ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            conversation.append(HumanMessage(content=user_input))

            try:
                result = agent.invoke({"messages": conversation})
            except SQLAlchemyError as e:
                print(f"\n[DB ERROR] {e}\nThe database operation failed. The conversation state has been reset.\n")
                conversation = []
                continue

            conversation = list(result["messages"])

            # Last message is the agent's response
            last = conversation[-1]
            print(f"\nAgent: {last.content}\n")

    except KeyboardInterrupt:
        print("\nGoodbye.")
    finally:
        inv_session.close()
        audit_session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
