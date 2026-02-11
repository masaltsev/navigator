
# coding: utf-8
import os
import json
import time
import math
import re
import requests
import pandas as pd
import random
from tqdm import tqdm
from dadata import Dadata

# Создаем папки для логов
os.makedirs("logs/requests", exist_ok=True)
os.makedirs("logs/processing", exist_ok=True)

# Настройки API
DADATA_TOKEN = os.getenv("DADATA_TOKEN")
DADATA_SECRET = os.getenv("DADATA_SECRET")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")  # Новый ключ для DeepSeek
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")  # Дефолтная модель DeepSeek

dadata = Dadata(DADATA_TOKEN, DADATA_SECRET)

# Загрузка справочников
with open("hp_listing_category.json", "r", encoding="utf-8") as f:
    CATEGORY_DICT = json.load(f)

with open("hp_listing_service.json", "r", encoding="utf-8") as f:
    SERVICE_DICT = json.load(f)

with open("hp_listing_type.json", "r", encoding="utf-8") as f:
    TYPE_DICT = json.load(f)

with open("hp_listing_cover.json", "r", encoding="utf-8") as f:
    COVER_DICT = json.load(f)

with open("hp_listing_ownership.json", "r", encoding="utf-8") as f:
    OWNERSHIP_DICT = json.load(f)

def load_reference_text(filename):
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [name for name in data.keys()]

CATEGORY_NAMES = load_reference_text("hp_listing_category.json")
SERVICE_NAMES = load_reference_text("hp_listing_service.json")
TYPE_NAMES = load_reference_text("hp_listing_type.json")
COVER_NAMES = load_reference_text("hp_listing_cover.json")
OWNERSHIP_NAMES = list(OWNERSHIP_DICT.keys())

def clean_inn_ogrn(value):
    """Приводит ИНН/ОГРН к целочисленному формату"""
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, (int, str)):
        try:
            # Удаляем все нецифровые символы
            cleaned = re.sub(r'\D', '', str(value))
            return int(cleaned) if cleaned else None
        except (ValueError, TypeError):
            return None
    return value

def clean_nan(obj):
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    elif isinstance(obj, float) and math.isnan(obj):
        return None
    else:
        return obj

def normalize_array_fields(card):
    array_fields = [
        'hp_phone', 'hp_email', 'hp_site',
        'hp_listing_category', 'hp_listing_service', 'hp_listing_type'
    ]
    
    for field in array_fields:
        if field not in card:
            card[field] = []
            continue
            
        value = card[field]
        
        if isinstance(value, str):
            card[field] = [value] if value.strip() != "" else []
        elif not isinstance(value, list):
            card[field] = [str(value)]
        elif any(not isinstance(item, str) for item in value):
            card[field] = [str(item) for item in value]
    
    return card

def process_dadata_response(d, card):
    opf_full = d.get("opf", {}).get("full", "")
    card["hp_listing_ownership"] = match_ownership(opf_full)
    
    if "address" in d and "data" in d["address"]:
        addr_data = d["address"]["data"]
        region_kladr = addr_data.get("region_kladr_id", "")
        if region_kladr and len(region_kladr) >= 2:
            try:
                card["hp_region"] = int(region_kladr[:2])
            except (ValueError, TypeError):
                pass
        
        card["hp_town"] = addr_data.get("city_with_type", "") or addr_data.get("settlement_with_type", "")
        card["hp_longitude"] = addr_data.get("geo_lon", "")
        card["hp_latitude"] = addr_data.get("geo_lat", "")
    
    if "contact" in d:
        dadata_phones = d["contact"].get("phones", [])
        if dadata_phones:
            current_phones = set(card.get("hp_phone", []))
            new_phones = [p["value"] for p in dadata_phones if p.get("value")]
            card["hp_phone"] = list(current_phones.union(new_phones))
        
        dadata_emails = d["contact"].get("emails", [])
        if dadata_emails:
            current_emails = set(card.get("hp_email", []))
            new_emails = [e["value"] for e in dadata_emails if e.get("value")]
            card["hp_email"] = list(current_emails.union(new_emails))
        
        dadata_sites = d["contact"].get("sites", [])
        if dadata_sites:
            current_sites = set(card.get("hp_site", []))
            new_sites = [s["value"] for s in dadata_sites if s.get("value")]
            card["hp_site"] = list(current_sites.union(new_sites))
    
    return card

def enrich_with_dadata(card):
    if card.get("hp_inn") or card.get("hp_ogrn"):
        org_id = card["hp_inn"] if card.get("hp_inn") else card["hp_ogrn"]
        try:
            data = dadata.find_by_id("party", str(org_id))
            if data and len(data) > 0:
                return process_dadata_response(data[0]["data"], card)
        except Exception as e:
            print(f"Dadata find_by_id error: {str(e)}")
    
    if card.get("post_title"):
        try:
            query = card["post_title"]
            filters = {}
            
            if card.get("hp_town"):
                town_clean = re.sub(r'^г\.?\s*', '', card["hp_town"], flags=re.IGNORECASE).strip()
                filters["locations"] = [{"city": town_clean}]
            
            suggestions = dadata.suggest(name="party", query=query, filters=filters, count=1)
            
            if suggestions and len(suggestions) > 0:
                return process_dadata_response(suggestions[0]["data"], card)
        except Exception as e:
            error_msg = f"Dadata suggest error: {str(e)}"
            if hasattr(e, 'response') and e.response:
                try:
                    error_msg += f" | Status: {e.response.status_code} | Response: {e.response.text[:200]}"
                except:
                    pass
            print(error_msg)
    
    return card

def match_ownership(opf_full):
    if not opf_full:
        return ""
    
    if opf_full in OWNERSHIP_NAMES:
        return opf_full
    
    opf_clean = re.sub(r'[^\w\s]', '', opf_full).strip().lower()
    
    for name in OWNERSHIP_NAMES:
        name_clean = re.sub(r'[^\w\s]', '', name).strip().lower()
        
        if opf_clean == name_clean:
            return name
        if opf_clean in name_clean or name_clean in opf_clean:
            return name
    
    return opf_full

def strict_match_array_field(values, reference_dict, reference_names):
    if not isinstance(values, list):
        values = [values] if values else []
    
    matched = []
    for v in values:
        if not v or pd.isna(v):
            continue
            
        if v in reference_names:
            matched.append(v)
            continue
            
        v_clean = re.sub(r'[^\w\s]', '', str(v)).strip().lower()
        found = False
        
        for name in reference_names:
            name_clean = re.sub(r'[^\w\s]', '', name).strip().lower()
            
            if v_clean == name_clean:
                matched.append(name)
                found = True
                break
            if v_clean in name_clean or name_clean in v_clean:
                matched.append(name)
                found = True
                break
                
    return list(set(matched))

def strict_match_single_field(value, reference_dict, reference_names):
    if not value or pd.isna(value):
        return ""
    
    if value in reference_names:
        return value
    
    v_clean = re.sub(r'[^\w\s]', '', str(value)).strip().lower()
    
    for name in reference_names:
        name_clean = re.sub(r'[^\w\s]', '', name).strip().lower()
        
        if v_clean == name_clean:
            return name
        if v_clean in name_clean or name_clean in v_clean:
            return name
    
    return ""

def parse_model_response(content):
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start_idx = content.find('{')
        end_idx = content.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            try:
                return json.loads(content[start_idx:end_idx])
            except:
                pass
        
        decision = "rejected"
        reason = "Невалидный ответ API"
        
        if "rejected" in content.lower():
            decision = "rejected"
        elif "accepted" in content.lower():
            decision = "accepted"
        
        if "причина" in content.lower():
            reason_match = re.search(r'причина[:\s]*(.*?)(\n|$)', content, re.IGNORECASE)
            if reason_match:
                reason = reason_match.group(1)
        
        return {
            "decision": decision,
            "reason": reason,
            "post_content": "Сгенерировать не удалось"
        }

def truncate_text(text, max_length):
    if not text or len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def save_api_log(request_data, response_data, idx, error=None):
    """Сохраняет лог запроса к API в формате JSON"""
    timestamp = int(time.time() * 1000)
    log_data = {
        "timestamp": timestamp,
        "index": idx,
        "request": request_data,
        "response": response_data,
        "error": error
    }
    
    filename = f"logs/requests/request_{idx}_{timestamp}.json"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        return filename
    except Exception as e:
        print(f"Ошибка сохранения лога запроса: {str(e)}")
        return None

def call_deepseek_model(card, instruction, idx):
    """Вызывает модель DeepSeek с сохранением лога запроса"""
    # Ограничение длины текстовых полей
    post_title = truncate_text(card.get("post_title", ""), 100)
    post_content = truncate_text(card.get("post_content", ""), 1500)
    
    context = {
        "id": card.get("id", ""),  # Добавлено поле ID
        "post_title": post_title,
        "post_content": post_content,
        "hp_dobro_ru": card.get("hp_dobro_ru", ""),
        "hp_inn": card.get("hp_inn", ""),
        "hp_ogrn": card.get("hp_ogrn", ""),
        "hp_site": card.get("hp_site", []),
        "hp_location": card.get("hp_location", ""),
        "hp_town": card.get("hp_town", ""),
        "hp_region": card.get("hp_region", ""),
        "Регион": card.get("Регион", "")  # Добавлено поле Регион
    }
    context = clean_nan(context)
    
    # Сокращенная инструкция
    ref_text = (
        "ДОСТУПНЫЕ КАТЕГОРИИ ПРОБЛЕМ:\n- " + 
        "\n- ".join(CATEGORY_NAMES) + 
        "\n\nДОСТУПНЫЕ УСЛУГИ:\n- " + 
        "\n- ".join(SERVICE_NAMES) +
        "\n\nДОСТУПНЫЕ ТИПЫ ОРГАНИЗАЦИЙ:\n- " + 
        "\n- ".join(TYPE_NAMES) +
        "\n\nДОСТУПНЫЕ УРОВНИ ПОКРЫТИЯ:\n- " + 
        "\n- ".join(COVER_NAMES)
    )
    
    enhanced_instruction = (
        f"{instruction}\n\n"
        "## КРИТИЧЕСКИ ВАЖНО:\n"
        "1. Используйте ТОЛЬКО названия из справочников\n"
        "2. В ответе ТОЛЬКО валидный JSON\n\n"
        f"{ref_text}"
    )
    
    user_message = "Данные организации:\n" + json.dumps(context, ensure_ascii=False, indent=2)

    # Логирование размера промпта
    prompt_size = len(enhanced_instruction) + len(user_message)
    print(f"Размер промпта: {prompt_size} символов (~{prompt_size//4} токенов)")

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": enhanced_instruction},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.1,
        "max_tokens": 3000,
        "stop": None
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            json_response = response.json()
            
            # Сохраняем лог запроса
            log_filename = save_api_log(payload, json_response, idx)
            
            # Извлечение контента из структуры ответа
            content = json_response["choices"][0]["message"]["content"]
            return parse_model_response(content), log_filename
        
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"Ошибка API ({error_msg}), повтор через {wait_time:.1f} сек")
                time.sleep(wait_time)
                continue
                
            if hasattr(e, 'response') and e.response:
                try:
                    error_details = e.response.json().get('error', {}).get('message', '')
                    error_msg += f" | Details: {error_details}"
                except:
                    error_msg += f" | Status: {e.response.status_code}"
            
            # Сохраняем лог ошибки
            log_filename = save_api_log(payload, None, idx, error_msg)
            return {"decision": "error", "reason": error_msg}, log_filename
            
        except Exception as e:
            error_msg = f"Processing error: {str(e)}"
            log_filename = save_api_log(payload, None, idx, error_msg)
            return {"decision": "error", "reason": error_msg}, log_filename

def append_to_log(log_path, logs_df):
    """Добавляет данные в CSV-лог с проверкой заголовков"""
    try:
        # Проверяем существование файла
        file_exists = os.path.isfile(log_path)
        
        # Режим записи: дополнение с заголовком только если файл новый
        mode = 'a' if file_exists else 'w'
        header = not file_exists
        
        logs_df.to_csv(log_path, mode=mode, header=header, index=False, encoding="utf-8")
        return True
    except Exception as e:
        print(f"Ошибка записи в лог: {str(e)}")
        return False

def process_cards(input_file, output_file, log_file, instruction_file, batch_size=20):
    # Генерируем уникальный ID для этого запуска
    run_id = int(time.time())
    print(f"Начало обработки. ID запуска: {run_id}")
    
    df = pd.read_excel(input_file)
    accepted_cards = []
    rejected_cards = []
    error_cards = []
    logs = []

    with open(instruction_file, "r", encoding="utf-8") as f:
        instruction = f.read()

    for idx, row in tqdm(df.iterrows(), total=len(df)):
        start_time = time.time()
        card = clean_nan(row.to_dict())
        original_card = card.copy()
        
        # Сохраняем ID из входных данных
        card["id"] = card.get("id", "")
        
        # Сохраняем dobro.ru ссылку
        if "dobro.ru link" in card:
            card["hp_dobro_ru"] = card["dobro.ru link"]
        elif "hp_dobro_ru" in card:
            card["hp_dobro_ru"] = card["hp_dobro_ru"]
        else:
            card["hp_dobro_ru"] = ""
        
        # Обработка контактных данных
        if "Email" in card:
            card["hp_email"] = card["Email"]
        if "telephone" in card:
            card["hp_phone"] = card["telephone"]
        
        # Очистка ИНН/ОГРН
        for field in ["hp_inn", "hp_ogrn"]:
            if field in card:
                card[field] = clean_inn_ogrn(card[field])
        
        region_id = None
        if "region id" in card:
            region_id = card["region id"]
        elif "region_id" in card:
            region_id = card["region_id"]
        
        card = normalize_array_fields(card)
        card_before_dadata = card.copy()
        card = enrich_with_dadata(card)
        card = clean_nan(card)
        
        contact_fields = ["hp_phone", "hp_email", "hp_site"]
        for field in contact_fields:
            original_values = set(card_before_dadata.get(field, []))
            dadata_values = set(card.get(field, []))
            combined = list(original_values.union(dadata_values))
            card[field] = combined
        
        card = normalize_array_fields(card)
        
        if "hp_region" not in card and region_id is not None:
            try:
                region_str = str(region_id)
                digits = re.sub(r'\D', '', region_str)
                if len(digits) >= 2:
                    card["hp_region"] = int(digits[:2])
            except (ValueError, TypeError):
                pass
        
        log_entry = {
            "run_id": run_id,  # Уникальный ID запуска
            "index": idx,
            "title": card.get("post_title", ""),
            "inn": card.get("hp_inn", ""),
            "ogrn": card.get("hp_ogrn", ""),
            "decision": "pending",
            "reason": "",
            "start_timestamp": start_time,  # Время начала обработки
            "processing_time": 0,  # Время обработки в секундах
            "model": MODEL_NAME,
            "request_log": ""  # Путь к логу запроса
        }

        try:
            response, request_log_filename = call_deepseek_model(card, instruction, idx)
            log_entry["request_log"] = request_log_filename or ""
            
            model_fields = [
                "post_content", "hp_listing_category", "hp_listing_service",
                "hp_listing_type", "hp_listing_cover", "decision", "reason"
            ]
            
            for field in model_fields:
                if field in response:
                    card[field] = response[field]
            
            # Сохранение оригинальных ID и ссылки dobro.ru
            card["id"] = original_card.get("id", "")
            card["hp_dobro_ru"] = original_card.get("hp_dobro_ru", "")
            
            card = normalize_array_fields(card)
            
            card["hp_listing_category"] = strict_match_array_field(
                card["hp_listing_category"], CATEGORY_DICT, CATEGORY_NAMES
            )
            
            card["hp_listing_service"] = strict_match_array_field(
                card["hp_listing_service"], SERVICE_DICT, SERVICE_NAMES
            )
            
            card["hp_listing_type"] = strict_match_array_field(
                card["hp_listing_type"], TYPE_DICT, TYPE_NAMES
            )
            
            card["hp_listing_cover"] = strict_match_single_field(
                card.get("hp_listing_cover", ""),
                COVER_DICT,
                COVER_NAMES
            )
            
            card = normalize_array_fields(card)
            
            fields_to_remove = [
                "Email", "telephone", "dobro.ru link",
                "Регион", "region id", "region_id", "region"
            ]
            for field in fields_to_remove:
                if field in card:
                    del card[field]
            
            processing_time = round(time.time() - start_time, 2)
            card["generation_time"] = processing_time
            log_entry["processing_time"] = processing_time
            log_entry["decision"] = response.get("decision", "error")
            log_entry["reason"] = response.get("reason", "")
            
            decision = response.get("decision", "").lower()
            if decision == "accepted":
                accepted_cards.append(card)
            elif decision == "rejected":
                rejected_cards.append(card)
            else:
                error_cards.append(card)
                
        except Exception as e:
            processing_time = round(time.time() - start_time, 2)
            log_entry["decision"] = "error"
            log_entry["reason"] = str(e)
            log_entry["processing_time"] = processing_time
            error_cards.append(card)
            
        logs.append(log_entry)

    final_output = {
        "accepted": accepted_cards,
        "rejected": rejected_cards,
        "errors": error_cards
    }
    
    with open(output_file, "w", encoding="utf-8") as f_out:
        json.dump(final_output, f_out, ensure_ascii=False, indent=2)
    
    # Сохраняем лог обработки в режиме дополнения
    log_path = os.path.join("logs/processing", os.path.basename(log_file))
    logs_df = pd.DataFrame(logs)
    
    # Создаем папку если нужно
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    # Дополняем существующий файл или создаем новый
    if append_to_log(log_path, logs_df):
        print(f"Лог обработки дополнен: {log_path}")
    else:
        print("Ошибка при записи лога обработки")
    
    print("\nОбработка завершена. Статистика:")
    print(f"Принято организаций: {len(accepted_cards)}")
    print(f"Отклонено организаций: {len(rejected_cards)}")
    print(f"Ошибок обработки: {len(error_cards)}")
    total_time = sum(log['processing_time'] for log in logs)
    print(f"Общее время: {total_time:.2f} сек")
    print(f"Среднее время на карточку: {total_time / len(logs):.2f} сек")

if __name__ == "__main__":
    process_cards(
        input_file="dobro_orgs.xlsx",
        output_file="deepseek_results.json",
        log_file="deepseek_processing_log.csv",
        instruction_file="full_instruction_v5.md",
        batch_size=20
    )