"""Bounded PDF/TXT text extraction; a scan requires a text layer (no OCR)."""
import re
import fitz

MAX_FILE_BYTES = 8 * 1024 * 1024


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
    elif filename.endswith('.txt'):
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError("TXT должен быть в кодировке UTF-8") from exc
    else:
        raise ValueError("Неподдерживаемый формат. Загрузите PDF или TXT")
    text = re.sub(r'(?<=[а-яё])(?=[А-ЯЁ])', ' ', text)
    text = re.sub(r'\n+', '\n', text).strip()
    if len(text) > 1_000_000:
        raise ValueError("Извлечённый текст превышает допустимый миллион символов")
    if not text:
        raise ValueError("Текст не обнаружен. Для PDF-скана нужен текстовый слой")
    return text
