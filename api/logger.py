import logging
import os


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
        log_file = os.path.join(os.getcwd(), 'app.log')
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger