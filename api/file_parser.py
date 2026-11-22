"""Extract document text within the upload and text size limits."""
from io import BytesIO
import re
from xml.parsers import expat
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

import pymupdf as fitz

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 1_000_000
_MAX_DOCX_XML_BYTES = 16 * 1024 * 1024
_WORD_NAMESPACES = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}
_INVALID_DOCX = "DOCX повреждён или имеет неверный формат"


def _docx_text(content: bytes) -> str:
    """Read paragraphs, including table cells, from the main Word document."""
    parser = expat.ParserCreate(namespace_separator="}")
    parser.buffer_text = True
    elements: list[str] = []
    parts: list[str] = []
    prefix = ""
    body_found = False
    body_open = False
    text_chars = 0

    def append(value: str) -> None:
        nonlocal text_chars
        text_chars += len(value)
        if text_chars > MAX_TEXT_CHARS:
            raise ValueError("Извлечённый текст превышает допустимый миллион символов")
        parts.append(value)

    def start(tag: str, _: dict) -> None:
        nonlocal prefix, body_found, body_open
        if not elements:
            namespace, separator, name = tag.partition("}")
            if not separator or namespace not in _WORD_NAMESPACES or name != "document":
                raise ValueError(_INVALID_DOCX)
            prefix = namespace + separator
        elif len(elements) == 1 and tag == prefix + "body":
            body_found = body_open = True
        if len(elements) >= 256:
            raise ValueError(_INVALID_DOCX)
        elements.append(tag)
        if body_open and tag in (prefix + "br", prefix + "cr", prefix + "tab"):
            append("\t" if tag == prefix + "tab" else "\n")

    def end(tag: str) -> None:
        nonlocal body_open
        if body_open and tag == prefix + "p":
            append("\n")
        if len(elements) == 2 and tag == prefix + "body":
            body_open = False
        elements.pop()

    def text(value: str) -> None:
        if body_open and elements[-1] == prefix + "t":
            append(value)

    def reject_doctype(*_) -> None:
        raise ValueError(_INVALID_DOCX)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text
    parser.StartDoctypeDeclHandler = reject_doctype

    try:
        with ZipFile(BytesIO(content)) as archive:
            archive.getinfo("[Content_Types].xml")
            main = archive.getinfo("word/document.xml")
            if main.file_size > _MAX_DOCX_XML_BYTES:
                raise ValueError("Содержимое DOCX превышает допустимый размер 16 МиБ")
            with archive.open(main) as xml:
                while chunk := xml.read(64 * 1024):
                    parser.Parse(chunk, False)
                parser.Parse(b"", True)
    except (BadZipFile, KeyError, EOFError, RuntimeError, NotImplementedError, ZlibError, expat.ExpatError) as exc:
        raise ValueError(_INVALID_DOCX) from exc
    if not body_found:
        raise ValueError(_INVALID_DOCX)
    return "".join(parts)


def extract_text_from_file(content: bytes, filename: str) -> str:
    if not content:
        raise ValueError("Файл пуст")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("Файл превышает допустимый размер 8 МиБ")
    filename = (filename or "").lower()
    if filename.endswith('.pdf'):
        try:
            with fitz.open(stream=content, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise ValueError("PDF защищён паролем")
                if doc.page_count > 200:
                    raise ValueError("PDF превышает допустимые 200 страниц")
                blocks = [block[4].strip() for page in doc
                          for block in page.get_text("blocks") if block[4].strip()]
                text = "\n".join(blocks)
        except (RuntimeError, fitz.FileDataError) as exc:
            raise ValueError("PDF повреждён или имеет неверный формат") from exc
    elif filename.endswith('.docx'):
        text = _docx_text(content)
    elif filename.endswith('.txt'):
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError("TXT должен быть в кодировке UTF-8") from exc
    else:
        raise ValueError("Неподдерживаемый формат. Загрузите PDF, DOCX или TXT")
    text = re.sub(r'(?<=[а-яё])(?=[А-ЯЁ])', ' ', text)
    text = re.sub(r'\n+', '\n', text).strip()
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("Извлечённый текст превышает допустимый миллион символов")
    if not text:
        if filename.endswith('.pdf'):
            raise ValueError("Текст не обнаружен. Для PDF-скана нужен текстовый слой")
        raise ValueError("Текст в документе не обнаружен")
    return text
