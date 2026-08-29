
#ЭКСПЕРИМЕНТАЛЬНЫЙ СКРИПТ - НЕ РАБОТАЕТ
#Попытка автоматического парсинга SuperJob.ru
#Не сработал из-за блокировок сайта и изменения CSS-селекторов
#Датасет собран вручную



import requests
from bs4 import BeautifulSoup
import json
import time
import re

def parse_superjob(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Извлекаем ID из ссылки
        vacancy_id = re.search(r'-(\d+)\.html', url)
        vac_id = f"sj_{vacancy_id.group(1)}" if vacancy_id else f"sj_unknown_{int(time.time())}"
        
        # Извлекаем данные
        title = soup.find('h1')
        title_text = title.text.strip() if title else "Не указано"
        
        # Описание вакансии
        description = soup.find('div', class_='vacancy-description')
        # Очищаем текст от лишних переносов строк
        text = description.get_text(separator=' ', strip=True) if description else "Текст не найден"
        
        # Город
        city = soup.find('span', class_='vacancy-city')
        city_text = city.text.strip() if city else "Не указано"
        
        # Дата
        date = soup.find('span', class_='vacancy-date')
        date_text = date.text.strip() if date else "Не указана"

        return {
            "id": vac_id,
            "source": "superjob",
            "title": title_text,
            "text": text,
            "city": city_text,
            "date": date_text,
            "expected_skills": []
        }
    except Exception as e:
        print(f"Ошибка при парсинге {url}: {e}")
        return None

# Читаем ссылки из файла
with open('data/urls.txt', 'r', encoding='utf-8') as f:
    urls = [line.strip() for line in f if line.strip()]

dataset = []
print(f"Начинаем сбор {len(urls)} вакансий...")

for i, url in enumerate(urls):
    print(f"Обработка {i+1}/{len(urls)}: {url}")
    vacancy_data = parse_superjob(url)
    if vacancy_data:
        dataset.append(vacancy_data)
    time.sleep(1.5) # Пауза

with open('data/superjob_dataset.json', 'w', encoding='utf-8') as f:
    json.dump(dataset, f, ensure_ascii=False, indent=2)

print(f"Сохранено {len(dataset)} вакансий в data/superjob_dataset.json")