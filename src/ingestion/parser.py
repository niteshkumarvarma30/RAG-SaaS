import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter

def parse_pdf(pdf_bytes: bytes) -> str:
    """Extracts text from a raw PDF byte stream, stripping formatting."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    return text

def chunk_text(text: str) -> list[str]:
    """Chunks text logically using a recursive character splitter."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    return splitter.split_text(text)
