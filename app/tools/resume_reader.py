from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from typing import BinaryIO, Iterator


def read_docx_resume(file_path: str | BinaryIO) -> str:
    """Read body paragraphs and table cells in order, excluding headers/footers.

    Tables use row-major order; nested tables retain their position within cells.
    Deduplication is structural, not textual: repeated words in distinct cells
    remain useful evidence, while merged cells are visited only once.
    """
    document = Document(file_path)
    seen_cells = set()

    def iter_text(container) -> Iterator[str]:
        for block in container.iter_inner_content():
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if text:
                    yield text
            elif isinstance(block, Table):
                for row in block.rows:
                    for cell in row.cells:
                        # python-docx exposes merged grid positions as proxies
                        # for the same underlying XML cell, including row spans.
                        if cell._tc in seen_cells:
                            continue
                        seen_cells.add(cell._tc)
                        yield from iter_text(cell)

    return "\n".join(iter_text(document))
