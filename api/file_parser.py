import io
import re
import pdfplumber


def extract_text_from_file(content: bytes, filename: str) -> str:
    """
    Извлекает текст из загруженного файла (PDF или TXT).
    Безопасно считывает текст из PDF и расшивает склеенные слова.
    """
    if filename.lower().endswith('.pdf'):
        text_blocks = []

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                # 1. Извлекаем текст в стандартном режиме (без жесткой привязки к layout)
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_blocks.append(page_text)

        full_text = "\n".join(text_blocks)

        # 2. Страховка: расшиваем склеенные слова (CamelCase)
        clean_text = re.sub(r'(?<=[a-zа-яё])(?=[A-ZА-ЯЁ])', ' ', full_text)
        clean_text = re.sub(r'(?<=[a-zа-яё])(?=[0-9])', ' ', clean_text)

        # 3. Нормализуем множественные переносы строк и пробелы
        clean_text = re.sub(r'\n+', '\n', clean_text)

        return clean_text.strip()

    elif filename.lower().endswith('.txt'):
        return content.decode('utf-8', errors='ignore').strip()

    else:
        raise ValueError("Неподдерживаемый формат файла. Загрузите PDF или TXT.")