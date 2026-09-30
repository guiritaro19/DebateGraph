import re
import unicodedata

from langchain_text_splitters import RecursiveCharacterTextSplitter


def clean(text):
    return re.sub(r"[ \t]+", " ", unicodedata.normalize("NFKC", text)).strip()


def chunks(text):
    return RecursiveCharacterTextSplitter(
        chunk_size=1000, chunk_overlap=180, separators=["\n\n", "\n", ". ", " "]
    ).split_text(clean(text))
