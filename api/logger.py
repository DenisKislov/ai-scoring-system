import logging
from pathlib import Path


LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "app.log"


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    # Чтобы хендлеры не дублировались при перезагрузках
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # Строгий формат: Время | Уровень | Сообщение
        formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', datefmt='%H:%M:%S')

        # Вывод в консоль
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Запись в файл для фронтенда
        LOG_PATH.parent.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(LOG_PATH, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
