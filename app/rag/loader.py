"""Parse med_info.txt into one LangChain Document per numbered item.

Each item is a semantic unit (e.g. "1. LIDOCAINE 2% INJ.\n...").
Chunking by item number rather than fixed tokens preserves full clinical context.
"""

import re
from pathlib import Path

from langchain_core.documents import Document

MED_INFO_PATH = Path(__file__).parent.parent.parent / "case" / "med_info.txt"


def load_med_documents(path: Path = MED_INFO_PATH) -> list[Document]:
    """Split med_info.txt into one Document per numbered section."""
    text = path.read_text(encoding="utf-8")

    # Split on numbered headings: "1. NAME", "2. NAME", …
    # Pattern: newline or start of string followed by a digit and a period
    sections = re.split(r"(?=^\d+\. )", text, flags=re.MULTILINE)
    sections = [s.strip() for s in sections if s.strip()]

    docs = []
    for section in sections:
        # Extract item number and name from first line
        first_line = section.splitlines()[0]
        match = re.match(r"^(\d+)\.\s+(.+)$", first_line)
        item_num = match.group(1) if match else "?"
        item_name = match.group(2).strip() if match else first_line

        docs.append(
            Document(
                page_content=section,
                metadata={
                    "item_number": item_num,
                    "item_name": item_name,
                    "source": "med_info.txt",
                },
            )
        )

    return docs
