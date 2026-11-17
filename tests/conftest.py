"""Общие настройки тестов.

NER-навыки по умолчанию выключены для всего сьюта: старые тесты писались до
интеграции NER и проверяют словарное поведение. Тесты NER
(``test_ner_skills.py``) управляют флагом явно через ``monkeypatch.setenv``,
который перекрывает это значение. Продакшен-дефолт — ключ
``ner_skills_enabled`` в ``config/algorithm.json``; поведение «флаг включён»
дополнительно проверяется гейтом ``reports/ner_gate/``.
"""
import os

os.environ.setdefault("NER_SKILLS_ENABLED", "0")
