# Harvester v1 — Финальная спецификация: Crawl4AI + DeepSeek API
> **Проект:** Навигатор здорового долголетия  
> **Модуль:** Harvester + AI Pipeline (Phase 1 — обогащение org_website)  
> **Стек:** Python 3.12 · Crawl4AI 0.8.x · DeepSeek API (через LiteLLM) · Celery + Redis · PostgreSQL  
> **Дата:** 21 февраля 2026  
> **Связанные документы:**  
> - `docs/Navigator_Core_Model_and_API.md` — доменная модель и API  
> - `docs/AI_Pipeline_Navigator_Plan.md` — стратегия AI Pipeline и промптинга  
> - `backend/database/seeders/*Seeder.php` — справочники (single source of truth)

***
## 1. Концепция и цель Phase 1
Первый этап Harvester решает одну конкретную задачу: **обогащение уже заведённых в базу организаций**, у которых в таблице `sources` зафиксированы адреса официальных сайтов с типом `org_website`. Harvester последовательно обходит сайты, извлекает из них структурированные данные (описание, услуги, контакты, адреса, мероприятия) и выравнивает результаты в строгом соответствии с реляционной моделью Navigator Core — через закрытые словари-справочники.[^1][^2]

Phase 2 (агрегаторы: ФПГ, реестр СО НКО, Добро.рф) реализуется следующим шагом. Архитектура Harvester спроектирована расширяемо через `sources.kind` и `parseprofiles.crawl_strategy`, поэтому Phase 2 не потребует перестройки, а только добавления новых стратегий (`paginated_list`, `open_data_csv`) и логики `match_or_create` для новых организаций.[^2]

***
## 2. Обоснование выбора стека
### 2.1 Crawl4AI — основной инструмент краулинга и экстракции
Crawl4AI — полностью open-source (Apache 2.0) Python-фреймворк, 50 000+ звёзд на GitHub, спроектированный для генерации LLM-ready контента. Выбор обусловлен:[^3]

- **Нулевая стоимость** фреймворка — полный self-hosting, нет лицензионных платежей[^3]
- **Нативная поддержка DeepSeek** через LiteLLM — prefix `deepseek/deepseek-chat` + env `DEEPSEEK_API_KEY`[^4]
- **Три уровня экстракции**, позволяющие минимизировать токены: LLM-based (сложные страницы), CSS-based (типовые сайты — 0 токенов после генерации шаблона), Regex-based (телефоны, ИНН — 0 токенов)[^5][^6]
- **Playwright внутри** — headless-браузер со stealth-mode, proxy-ротацией, hooks[^7][^8]
- **Async-first** — `arun_many()` для параллельного краулинга[^6]
- **Python-нативность** — идеально интегрируется с Celery, Redis и архитектурой `deepseek_navigator.py`[^2]

Firecrawl Cloud ($16/мес Hobby-план) используется как **fallback** для ~10% сайтов, защищённых Cloudflare/DDoS-Guard, где встроенного stealth-режима Crawl4AI недостаточно.[^9][^10]
### 2.2 DeepSeek API Platform — LLM для экстракции и классификации
DeepSeek API обеспечивает оптимальный баланс стоимости и простоты на первом этапе, без необходимости развёртывания GPU-сервера для Ollama.[^11][^12]

| Параметр | DeepSeek-chat API | Ollama (local) |
|---|---|---|
| **Input tokens** | $0.14/1M (cache miss), $0.014/1M (cache hit) | ~$0 |
| **Output tokens** | $0.28/1M | ~$0 |
| **Стоимость 10K страниц** | $3–11 | ~$0 + аренда GPU |
| **DevOps overhead** | Нулевой | GPU-сервер, модели, обновления |
| **Кэширование промпта** | Автоматическое (системный промпт + сидеры) | Нет |

При ~10 000 страниц первого прохода стоимость — **$3–11**. Системный промпт с инъекцией справочников автоматически кэшируется DeepSeek, снижая input-стоимость в 10 раз при повторных вызовах.[^12][^13][^11]
### 2.3 Гибридная стратегия экстракции (три режима)
| Режим | Когда | Токены | Инструмент Crawl4AI |
|---|---|---|---|
| **Regex** | Телефоны, email, ИНН/ОГРН | 0 | `RegexExtractionStrategy` |
| **CSS Schema** | Типовые КЦСОН, поликлиники (после 1-й генерации шаблона) | 0 | `JsonCssExtractionStrategy` |
| **LLM** | Нестандартные сайты; описания; классификация | ~3 500/стр. | `LLMExtractionStrategy` |

Для типовых госсайтов — **однократная** генерация CSS-схемы через LLM, дальше экстракция без токенов. Для нестандартных — LLM через DeepSeek API.[^6]

***
## 3. Структура проекта
Harvester размещается в существующей папке `ai-pipeline/`, на одном уровне с `backend/` (Laravel).

```
navigator/
├── backend/                              # Laravel Navigator Core
│   ├── app/
│   │   └── Console/Commands/
│   │       └── ExportSeedersJson.php     # ← Новая artisan-команда
│   ├── database/seeders/
│   │   ├── ThematicCategorySeeder.php    # Single source of truth
│   │   ├── ServiceSeeder.php
│   │   ├── OrganizationTypeSeeder.php
│   │   ├── SpecialistProfileSeeder.php
│   │   └── OwnershipTypeSeeder.php
│   └── ...
│
├── ai-pipeline/                          # ← Существующая папка
│   ├── harvester/                        # Crawl4AI + DeepSeek модуль
│   │   ├── pyproject.toml
│   │   ├── .env
│   │   │
│   │   ├── seeders_data/                 # JSON-экспорт из Laravel seeders
│   │   │   ├── thematic_categories.json
│   │   │   ├── services.json
│   │   │   ├── organization_types.json
│   │   │   ├── specialist_profiles.json
│   │   │   └── ownership_types.json
│   │   │
│   │   ├── config/
│   │   │   ├── settings.py              # Pydantic Settings (env vars)
│   │   │   ├── llm_config.py            # LLMConfig factory (DeepSeek)
│   │   │   └── seeders.py               # Загрузка справочников JSON → Pydantic
│   │   │
│   │   ├── schemas/
│   │   │   ├── extraction.py            # RawOrganizationData (промежуточная)
│   │   │   ├── navigator_core.py        # OrganizationImportPayload (финальная)
│   │   │   └── css_templates/           # Кэшированные CSS-схемы типовых сайтов
│   │   │       ├── kcson_template.json
│   │   │       └── poliklinika_template.json
│   │   │
│   │   ├── strategies/
│   │   │   ├── strategy_router.py       # Regex → CSS → LLM (определение режима)
│   │   │   ├── regex_strategy.py        # Телефоны, email, ИНН (0 токенов)
│   │   │   ├── css_strategy.py          # JsonCssExtractionStrategy (0 токенов)
│   │   │   ├── llm_strategy.py          # LLMExtractionStrategy + DeepSeek
│   │   │   └── multi_page.py            # Обход подстраниц (Услуги, Контакты, О нас)
│   │   │
│   │   ├── prompts/                     # ← Stub: промпты разрабатываются отдельно
│   │   │   ├── README.md                # Ссылка на AI_Pipeline_Navigator_Plan.md
│   │   │   ├── base_system_prompt.py    # Базовый скелет, инъекция сидеров
│   │   │   └── prompt_registry.py       # Реестр + загрузчик полиморфных промптов
│   │   │
│   │   ├── enrichment/
│   │   │   ├── classifier.py            # Маппинг на seeders (code-based)
│   │   │   ├── dadata_client.py         # Геокодирование через Dadata
│   │   │   ├── confidence_scorer.py     # ai_confidence_score
│   │   │   └── payload_builder.py       # Сборка JSON для Core API
│   │   │
│   │   ├── workers/
│   │   │   ├── celery_app.py            # Celery configuration
│   │   │   └── tasks.py                 # Celery tasks
│   │   │
│   │   ├── core_client/
│   │   │   ├── api.py                   # HTTP-клиент к Navigator Core Internal API
│   │   │   └── source_loader.py         # GET /api/internal/sources?due=true
│   │   │
│   │   ├── scripts/
│   │   │   ├── generate_css_schema.py   # Одноразовая генерация CSS-шаблонов
│   │   │   ├── seed_test_sources.py     # Заполнение тестовых sources
│   │   │   └── run_single_url.py        # CLI для отладки одного URL
│   │   │
│   │   ├── tests/
│   │   │   ├── test_strategies.py
│   │   │   ├── test_classifier.py
│   │   │   ├── test_payload_builder.py
│   │   │   └── fixtures/                # HTML-снапшоты реальных сайтов
│   │   │       ├── kcson_anapa.html
│   │   │       └── nko_dobro.html
│   │   │
│   │   ├── Dockerfile
│   │   └── docker-compose.yml           # harvester + redis
│   │
│   └── (будущее: event_parser/, aggregator_crawler/...)
│
└── docker-compose.yml                    # Общий compose (опционально)
```

***
## 4. Справочники (Seeders) — мост между Laravel и Python
### 4.1 Принцип: Single Source of Truth в Laravel, JSON-экспорт для Python
Справочники определены в PHP-сидерах (`backend/database/seeders/`). Они — **единственный источник правды** для кодов классификации. Python Harvester получает их в виде JSON-файлов, а не парсит PHP.[^14][^15][^16][^17][^18]
### 4.2 Реальные справочники (из PHP-сидеров)
**ThematicCategory** — иерархическая, 3 корня + 18 дочерних:[^15]
```
3  Здоровье и уход
├── 7   Снижение памяти и деменция
├── 8   Остеопороз и риски падений
├── 9   Урологические состояния
├── 10  Управление болью
├── 11  Питание и диета
├── 12  Зрение и здоровье глаз
├── 14  Восстановление после инсульта
├── 15  Травмы и реабилитация
├── 16  Слух и слухопротезирование
└── 17  Паллиативная помощь

4  Быт и социальная поддержка
├── 18  Нуждаемость в постороннем уходе
└── 20  Одинокое проживание

5  Активная жизнь
├── 24  Поддержание здоровья и ЗОЖ
├── 25  Общение и социализация
├── 26  Карьера и образование
├── 27  Уход за собой и стиль
├── 28  Творчество и увлечения
└── 29  Путешествия и туризм
```

Harvester маппит на **дочерние** коды (7–29), не на корневые (3, 4, 5).

**Service** — 44 услуги, коды 21–136. Включает бывшие тематические (21, 22, 23). Исключены мусорные коды 72, 81, 89, 107.[^16]

**OrganizationType** — 16 типов, коды 65–140:[^14]
```
65  ПНИ / Интернат          99   Кризисный центр
69  Культурное учреждение    103  Реабилитационный центр
71  Модельное агентство      112  Спец. стационар (деменция)
73  Косметологический центр  118  Хоспис / Паллиативное
79  Центр занятости          121  Сурдологический центр
82  Досуговый центр          124  Урологическое отделение
92  Клуб/Центр здоровья      138  Мед. школа для пациентов
                             139  Клиника памяти
                             140  Гериатрическое отделение
```

**SpecialistProfile** — 16 профилей, коды 96–143:[^17]
```
96   Волонтер                129  Физиотерапевт
120  Офтальмолог             130  Реабилитолог
122  Сурдолог                132  Ревматолог
123  ЛОР                     134  Травматолог-ортопед
125  Уролог                  137  Эндокринолог
126  Диетолог / Нутрициолог  141  Психиатр / Геронтопсихиатр
127  Мануальный терапевт     142  Невролог
128  Эрготерапевт            143  Гериатр
```

**OwnershipType** — 17 типов, коды 151–167:[^18]
```
152  ГАУ субъекта РФ         161  Фонд
153  МБУ                     162  АНО
154  ГБУ субъекта РФ         163  ООО (НЕ некоммерческая!)
155  Профсоюзная организация 164  ФГБУ
156  Учреждение              165  Общественная организация
157  Учреждение субъекта РФ  166  МАУ
158  Непубличное АО          167  МКУ
159  ГКУ субъекта РФ
160  Филиал юр. лица
```
⚠️ **Код 151 «Тест ОПФ» — исключить из маппинга!**
### 4.3 Laravel artisan-команда для экспорта
```php
// backend/app/Console/Commands/ExportSeedersJson.php
<?php

namespace App\Console\Commands;

use App\Models\{ThematicCategory, Service, OrganizationType, SpecialistProfile, OwnershipType};
use Illuminate\Console\Command;

class ExportSeedersJson extends Command
{
    protected $signature = 'seeders:export-json';
    protected $description = 'Export active seeders to JSON for AI Pipeline';

    public function handle(): void
    {
        $outputDir = base_path('../ai-pipeline/harvester/seeders_data');
        if (!is_dir($outputDir)) {
            mkdir($outputDir, 0755, true);
        }

        // ThematicCategory — с parent_code
        $categories = ThematicCategory::where('is_active', true)->get()->map(function ($cat) {
            return [
                'id'          => $cat->id,
                'code'        => $cat->code,
                'name'        => $cat->name,
                'is_active'   => $cat->is_active,
                'parent_code' => $cat->parent ? $cat->parent->code : null,
            ];
        });
        $this->writeJson($outputDir, 'thematic_categories.json', $categories);

        // Остальные — плоские
        $this->exportFlat($outputDir, 'services.json', Service::class);
        $this->exportFlat($outputDir, 'organization_types.json', OrganizationType::class);
        $this->exportFlat($outputDir, 'specialist_profiles.json', SpecialistProfile::class);

        // OwnershipType — исключаем тестовый код 151
        $ownership = OwnershipType::where('is_active', true)
            ->where('code', '!=', '151')
            ->get(['id', 'code', 'name', 'is_active']);
        $this->writeJson($outputDir, 'ownership_types.json', $ownership);

        $this->info('✅ Seeders exported to ai-pipeline/harvester/seeders_data/');
    }

    private function exportFlat(string $dir, string $filename, string $model): void
    {
        $data = $model::where('is_active', true)->get(['id', 'code', 'name', 'is_active']);
        $this->writeJson($dir, $filename, $data);
    }

    private function writeJson(string $dir, string $filename, $data): void
    {
        file_put_contents(
            "$dir/$filename",
            json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)
        );
    }
}
```

Вызов: `php artisan seeders:export-json` после каждого `php artisan db:seed`.
### 4.4 Python-загрузчик справочников
```python
# ai-pipeline/harvester/config/seeders.py
import json
from pathlib import Path
from pydantic import BaseModel

SEEDERS_DIR = Path(__file__).parent.parent / "seeders_data"

class SeederItem(BaseModel):
    id: int | None = None
    code: str
    name: str
    is_active: bool = True
    parent_code: str | None = None  # Только для ThematicCategory

class NavigatorSeeders(BaseModel):
    thematic_categories: list[SeederItem]
    services: list[SeederItem]
    organization_types: list[SeederItem]
    specialist_profiles: list[SeederItem]
    ownership_types: list[SeederItem]

    @property
    def child_categories(self) -> list[SeederItem]:
        """Только дочерние категории (для маппинга — не корневые 3/4/5)."""
        return [c for c in self.thematic_categories if c.parent_code is not None]

def load_seeders() -> NavigatorSeeders:
    """Загрузка из JSON-файлов в seeders_data/."""
    return NavigatorSeeders(
        thematic_categories=_load("thematic_categories.json"),
        services=_load("services.json"),
        organization_types=_load("organization_types.json"),
        specialist_profiles=_load("specialist_profiles.json"),
        ownership_types=_load("ownership_types.json"),
    )

def _load(filename: str) -> list[SeederItem]:
    with open(SEEDERS_DIR / filename) as f:
        return [SeederItem(**item) for item in json.load(f) if item.get("is_active", True)]
```

***
## 5. Конфигурация и подключение DeepSeek
### 5.1 Переменные окружения (.env)
```bash
# LLM
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEEPSEEK_MODEL=deepseek/deepseek-chat      # LiteLLM prefix

# Navigator Core Internal API
CORE_API_URL=https://api.navigator.vnuki.fund
CORE_API_TOKEN=Bearer xxxxx

# Dadata
DADATA_API_KEY=xxxxxxxx
DADATA_SECRET_KEY=xxxxxxxx

# Redis (Celery)
REDIS_URL=redis://localhost:6379/0

# Crawl4AI
CRAWL4AI_HEADLESS=true
CRAWL4AI_USER_AGENT=NavigatorHarvester/1.0 (+https://navigator.vnuki.fund)

# Fallback (Firecrawl Cloud — для заблокированных сайтов)
FIRECRAWL_API_KEY=fc-xxxxx
```
### 5.2 LLM Configuration Factory
```python
# ai-pipeline/harvester/config/llm_config.py
import os
from crawl4ai import LLMConfig

def get_llm_config() -> LLMConfig:
    """
    DeepSeek через LiteLLM. Кэширование системного промпта автоматическое —
    при повторных вызовах с одинаковым system prompt DeepSeek снижает
    input-стоимость до $0.014/1M (вместо $0.14/1M).
    """
    return LLMConfig(
        provider=os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat"),
        api_token=os.getenv("DEEPSEEK_API_KEY"),
    )
```
### 5.3 Зависимости (pyproject.toml)
```toml
[project]
name = "navigator-harvester"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "crawl4ai>=0.8.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "celery[redis]>=5.3",
    "httpx>=0.27",
    "tenacity>=8.0",       # Retry logic
    "structlog>=24.0",     # Structured logging
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff", "mypy"]
firecrawl = ["firecrawl-py>=1.0"]  # Опциональный fallback
```

***
## 6. Pydantic-схемы
### 6.1 Промежуточная модель (что LLM извлекает из HTML)
```python
# ai-pipeline/harvester/schemas/extraction.py
from pydantic import BaseModel, Field

class RawOrganizationData(BaseModel):
    """
    Промежуточная модель — результат LLM-экстракции.
    Поля «свободные». Маппинг на коды сидеров — в classifier.py (следующий шаг).
    """
    title: str = Field(..., description="Полное название организации")
    short_description: str = Field(default="", description="Краткое описание (2-3 предложения)")
    full_description: str = Field(default="", description="Полное описание деятельности")
    services_mentioned: list[str] = Field(default=[], description="Упомянутые услуги и сервисы")
    target_audiences: list[str] = Field(default=[], description="Целевые аудитории")
    specialist_types: list[str] = Field(default=[], description="Типы специалистов")
    phones: list[str] = Field(default=[], description="Телефоны")
    emails: list[str] = Field(default=[], description="Email-адреса")
    addresses: list[str] = Field(default=[], description="Полные адреса (город, улица, дом)")
    working_hours: str = Field(default="", description="Режим работы")
    inn: str = Field(default="", description="ИНН (10 или 12 цифр)")
    ogrn: str = Field(default="", description="ОГРН (13 или 15 цифр)")
    organization_type_hints: list[str] = Field(
        default=[], description="Тип: КЦСОН, поликлиника, фонд, НКО..."
    )
    works_with_elderly_evidence: str = Field(
        default="", description="Цитата/факт подтверждающий работу с пожилыми"
    )
    events_found: list[dict] = Field(
        default=[], description="Мероприятия: название, дата, описание, периодичность"
    )
```
### 6.2 Финальный payload для Navigator Core API
```python
# ai-pipeline/harvester/schemas/navigator_core.py
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class AiDecision(str, Enum):
    accepted = "accepted"
    rejected = "rejected"

class VenuePayload(BaseModel):
    address_raw: str
    fias_id: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_lon: Optional[float] = None
    is_headquarters: bool = False

class AiMetadata(BaseModel):
    decision: AiDecision
    ai_confidence_score: float = Field(ge=0.0, le=1.0)
    works_with_elderly: bool
    ai_explanation: Optional[str] = None
    ai_source_trace: Optional[dict] = None

class ClassificationPayload(BaseModel):
    """
    Коды из справочников. Используются code (строка), а не id (int),
    т.к. code стабилен между окружениями.
    """
    thematic_category_codes: list[str] = []     # Дочерние: "7", "24"...
    service_codes: list[str] = []                # "66", "91"...
    organization_type_codes: list[str] = []      # "103", "140"...
    specialist_profile_codes: list[str] = []     # "143", "142"...
    ownership_type_code: Optional[str] = None    # "154", "162"...
    coverage_level_id: Optional[int] = None

class OrganizationImportPayload(BaseModel):
    """
    Точно соответствует POST /api/internal/import/organizer
    из Navigator_Core_Model_and_API.md
    """
    source_reference: str
    entity_type: str = "Organization"
    title: str
    description: Optional[str] = None
    inn: Optional[str] = Field(None, max_length=12)
    ogrn: Optional[str] = Field(None, max_length=15)
    ai_metadata: AiMetadata
    classification: ClassificationPayload
    venues: list[VenuePayload] = []
```

***
## 7. Стратегии экстракции
### 7.1 Strategy Router — определение режима
```python
# ai-pipeline/harvester/strategies/strategy_router.py
import json
from pathlib import Path
from crawl4ai import LLMExtractionStrategy, JsonCssExtractionStrategy, CrawlerRunConfig
from config.llm_config import get_llm_config
from schemas.extraction import RawOrganizationData
from prompts.prompt_registry import get_extraction_prompt

CSS_TEMPLATES_DIR = Path("schemas/css_templates")

class StrategyRouter:
    """
    Определяет оптимальную стратегию для источника.
    Приоритет: CSS-шаблон (0 токенов) → LLM (DeepSeek API).
    Regex применяется всегда как дополнительный слой для контактов.
    """
    
    def __init__(self):
        self.llm_config = get_llm_config()
        self._css_cache: dict[str, dict] = {}
        self._load_css_templates()
    
    def _load_css_templates(self):
        for f in CSS_TEMPLATES_DIR.glob("*.json"):
            with open(f) as fh:
                self._css_cache[f.stem] = json.load(fh)
    
    def get_extraction_config(
        self, 
        source_kind: str,
        parse_profile_config: dict,
    ) -> CrawlerRunConfig:
        css_template = parse_profile_config.get("css_template")
        
        if css_template and css_template in self._css_cache:
            strategy = JsonCssExtractionStrategy(
                schema=self._css_cache[css_template]
            )
        else:
            # LLM-экстракция с Pydantic-схемой
            instruction = get_extraction_prompt(source_kind, parse_profile_config)
            strategy = LLMExtractionStrategy(
                llm_config=self.llm_config,
                schema=RawOrganizationData.model_json_schema(),
                extraction_type="schema",
                instruction=instruction,
                extra_args={"temperature": 0.0, "max_tokens": 2000},
                chunk_token_threshold=4000,
                overlap_rate=0.1,
            )
        
        return CrawlerRunConfig(
            extraction_strategy=strategy,
            word_count_threshold=10,
            page_timeout=30000,
        )
```
### 7.2 Regex-стратегия для контактных данных (0 токенов, применяется всегда)
```python
# ai-pipeline/harvester/strategies/regex_strategy.py
import re
from dataclasses import dataclass

@dataclass
class ContactExtraction:
    phones: list[str]
    emails: list[str]
    inn: str | None
    ogrn: str | None

PHONE_RE = re.compile(r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
INN_RE = re.compile(r"\bИНН[\s:]*(\d{10,12})\b", re.IGNORECASE)
OGRN_RE = re.compile(r"\bОГРН[\s:]*(\d{13,15})\b", re.IGNORECASE)

def extract_contacts(html: str) -> ContactExtraction:
    """Regex-экстракция контактных данных. 0 токенов, 0 API вызовов."""
    return ContactExtraction(
        phones=list(set(PHONE_RE.findall(html))),
        emails=list(set(EMAIL_RE.findall(html))),
        inn=next(iter(INN_RE.findall(html)), None),
        ogrn=next(iter(OGRN_RE.findall(html)), None),
    )
```
### 7.3 Multi-page навигация
```python
# ai-pipeline/harvester/strategies/multi_page.py
import asyncio
from urllib.parse import urljoin, urlparse
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode

SUBPAGE_PATTERNS = [
    "/uslugi", "/services", "/nashi-uslugi",
    "/kontakty", "/contacts",
    "/o-nas", "/about", "/ob-organizacii",
    "/raspisanie", "/schedule", "/rezhim-raboty",
    "/struktura", "/specialists",
]

class MultiPageCrawler:
    """
    Обходит главную + ключевые подстраницы организации.
    Объединяет результаты экстракции в единый RawOrganizationData.
    """
    
    def __init__(self, strategy_router):
        self.router = strategy_router
        self.browser_config = BrowserConfig(
            headless=True,
            enable_stealth=True,
            simulate_user=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
    
    async def crawl_organization(self, base_url: str, parse_config: dict) -> dict:
        async with AsyncWebCrawler(config=self.browser_config) as crawler:
            config = self.router.get_extraction_config("org_website", parse_config)
            config = config.clone(cache_mode=CacheMode.BYPASS)
            
            main_result = await crawler.arun(url=base_url, config=config)
            if not main_result.success:
                return {"error": main_result.error_message, "url": base_url}
            
            # Поиск и краул подстраниц
            subpages = self._find_subpages(base_url, main_result.links)
            sub_data = []
            if subpages:
                async for result in await crawler.arun_many(
                    subpages[:5], config=config.clone(stream=True)
                ):
                    if result.success:
                        sub_data.append(result)
            
            return self._merge(main_result, sub_data)
    
    def _find_subpages(self, base_url: str, links: list) -> list[str]:
        domain = urlparse(base_url).netloc
        found = set()
        for link in links.get("internal", []):
            href = link.get("href", "")
            full = urljoin(base_url, href)
            if urlparse(full).netloc != domain:
                continue
            path = urlparse(full).path.lower()
            if any(p in path for p in SUBPAGE_PATTERNS):
                found.add(full)
        return list(found)
    
    def _merge(self, main_result, sub_results: list) -> dict:
        import json
        data = json.loads(main_result.extracted_content or "{}")
        list_fields = [
            "services_mentioned", "phones", "emails",
            "addresses", "events_found", "specialist_types",
        ]
        text_fields = ["full_description", "working_hours", "inn", "ogrn"]
        
        for sub in sub_results:
            sub_data = json.loads(sub.extracted_content or "{}")
            for f in list_fields:
                if f in sub_data:
                    data[f] = list(set(data.get(f, []) + sub_data[f]))
            for f in text_fields:
                if not data.get(f) and sub_data.get(f):
                    data[f] = sub_data[f]
        return data
```

***
## 8. Полиморфные промпты — отдельный workstream
Разработка полиморфных промптов (Polymorphic Prompt Engineering) — **самостоятельный рабочий поток**, выполняемый в соответствии с рекомендациями из `AI_Pipeline_Navigator_Plan.md`. Она включает: контекстные промпты по типу организации (КЦСОН, НКО, поликлиника), Zero-Shot и Few-Shot примеры, темпоральный reasoning для мероприятий, инъекцию сидеров в контекст.[^1]

В коде Harvester заложена точка интеграции — папка `prompts/` со stub-файлами:
### 8.1 Базовый скелет промпта (stub)
```python
# ai-pipeline/harvester/prompts/base_system_prompt.py
"""
STUB — Полиморфные промпты разрабатываются отдельно
в соответствии с AI_Pipeline_Navigator_Plan.md (разделы:
Polymorphic Prompt Engineering, Temporal Reasoning, Schema-Constrained Extraction).

Этот файл содержит минимальный скелет для запуска Phase 1.
Полная система промптов заменит его на следующей итерации.
"""

from config.seeders import load_seeders

def build_base_system_prompt() -> str:
    """
    Минимальный системный промпт для Phase 1.
    Инъектирует справочники в контекст для Schema-Constrained Extraction.
    """
    seeders = load_seeders()
    
    # Формируем читаемый список услуг для LLM
    services_list = "\n".join(
        f"  - code:{s.code} → {s.name}" for s in seeders.services
    )
    categories_list = "\n".join(
        f"  - code:{c.code} → {c.name}" for c in seeders.child_categories
    )
    org_types_list = "\n".join(
        f"  - code:{t.code} → {t.name}" for t in seeders.organization_types
    )
    specialists_list = "\n".join(
        f"  - code:{s.code} → {s.name}" for s in seeders.specialist_profiles
    )
    
    return f"""Ты — специалист по анализу сайтов социальных и медицинских организаций России, работающих с пожилыми людьми.

ЗАДАЧА: Извлеки структурированную информацию об организации из HTML-страницы.

ПРАВИЛА КЛАССИФИКАЦИИ:
- Используй ТОЛЬКО коды из приведённых справочников.
- Если услуга/категория не имеет точного соответствия в справочнике — ПРОПУСТИ её.
- Никогда не выдумывай новые коды или названия.

СПРАВОЧНИК УСЛУГ (services):
{services_list}

СПРАВОЧНИК ТЕМАТИЧЕСКИХ КАТЕГОРИЙ (thematic_categories, только дочерние):
{categories_list}

СПРАВОЧНИК ТИПОВ ОРГАНИЗАЦИЙ (organization_types):
{org_types_list}

СПРАВОЧНИК СПЕЦИАЛИСТОВ (specialist_profiles):
{specialists_list}

Особое внимание обрати на признаки работы с пожилыми людьми:
программы активного долголетия, социальное обслуживание, реабилитация,
досуг для пенсионеров, серебряные волонтёры.

Если информация отсутствует — оставь поле пустым. Не додумывай."""
```
### 8.2 Реестр промптов (stub для будущей полиморфности)
```python
# ai-pipeline/harvester/prompts/prompt_registry.py
"""
STUB — Здесь будет реестр полиморфных промптов.
Полная реализация: отдельный workstream по AI_Pipeline_Navigator_Plan.md.
"""

from prompts.base_system_prompt import build_base_system_prompt

def get_extraction_prompt(source_kind: str, parse_config: dict) -> str:
    """
    Phase 1: единый промпт для всех org_website.
    
    Phase 2+ (TODO): полиморфные промпты по типу организации:
    - kcson_prompt → для КЦСОН (акцент на соц. услуги, надомное обслуживание)
    - medical_prompt → для поликлиник (акцент на специалистов, лицензии)
    - nko_prompt → для НКО/фондов (акцент на проекты, волонтёрство)
    - aggregator_prompt → для реестров (Phase 2)
    
    Переключение через parse_config["prompt_profile"] или авто-детекцию.
    """
    return build_base_system_prompt()
```

***
## 9. Обогащение и классификация
### 9.1 Classifier — маппинг на коды сидеров
```python
# ai-pipeline/harvester/enrichment/classifier.py
from config.seeders import NavigatorSeeders, SeederItem
from schemas.extraction import RawOrganizationData
from schemas.navigator_core import ClassificationPayload

# Маппинг аббревиатур ОПФ → code из OwnershipTypeSeeder
OWNERSHIP_PREFIX_MAP = {
    "ГАУ":   "152",  "ГАУСО": "152",
    "МБУ":   "153",
    "ГБУ":   "154",  "ГБУСО": "154", "ГБУЗ": "154",
    "ГКУ":   "159",  "ГКУСО": "159",
    "ФГБУ":  "164",  "ФГБОУ": "164",
    "МАУ":   "166",
    "МКУ":   "167",
    "АНО":   "162",
    "ФОНД":  "161",  "БФ": "161",
    "ООО":   "163",
    "ОО":    "165",  "РОО": "165", "МОО": "165", "НРОО": "165",
}

class SeederClassifier:
    """
    Маппит свободный текст из LLM-экстракции на закрытые коды справочников.
    LLM НЕ генерирует коды — только classifier.
    """
    
    def __init__(self, seeders: NavigatorSeeders):
        self.seeders = seeders
    
    def classify(self, raw: RawOrganizationData) -> ClassificationPayload:
        return ClassificationPayload(
            service_codes=self._match_services(raw.services_mentioned),
            thematic_category_codes=self._match_categories(raw),
            organization_type_codes=self._match_org_types(raw.organization_type_hints),
            specialist_profile_codes=self._match_specialists(raw.specialist_types),
            ownership_type_code=self._detect_ownership(raw.title),
        )
    
    def _match_services(self, mentioned: list[str]) -> list[str]:
        matched = []
        for mention in mentioned:
            m_lower = mention.lower().strip()
            best_match = self._fuzzy_match(m_lower, self.seeders.services)
            if best_match:
                matched.append(best_match.code)
        return list(set(matched))
    
    def _match_categories(self, raw: RawOrganizationData) -> list[str]:
        """Маппит на ДОЧЕРНИЕ категории (не корневые 3/4/5)."""
        text = f"{raw.short_description} {raw.full_description}".lower()
        matched = []
        for cat in self.seeders.child_categories:
            keywords = [w for w in cat.name.lower().split() if len(w) > 3]
            if any(kw in text for kw in keywords):
                matched.append(cat.code)
        return list(set(matched))
    
    def _match_org_types(self, hints: list[str]) -> list[str]:
        matched = []
        for hint in hints:
            best = self._fuzzy_match(hint.lower(), self.seeders.organization_types)
            if best:
                matched.append(best.code)
        return list(set(matched))
    
    def _match_specialists(self, types: list[str]) -> list[str]:
        matched = []
        for spec in types:
            best = self._fuzzy_match(spec.lower(), self.seeders.specialist_profiles)
            if best:
                matched.append(best.code)
        return list(set(matched))
    
    def _detect_ownership(self, title: str) -> str | None:
        """Определяет ОПФ по аббревиатуре в названии организации."""
        title_upper = title.upper().replace("«", "").replace("»", "").replace('"', '')
        for prefix, code in OWNERSHIP_PREFIX_MAP.items():
            if title_upper.startswith(prefix + " ") or f" {prefix} " in title_upper:
                return code
        return None
    
    @staticmethod
    def _fuzzy_match(query: str, items: list[SeederItem]) -> SeederItem | None:
        """Простой fuzzy match по пересечению ключевых слов."""
        best_item = None
        best_score = 0
        query_words = set(query.split())
        
        for item in items:
            if not item.is_active:
                continue
            item_words = set(item.name.lower().split())
            overlap = len(query_words & item_words)
            if overlap > best_score and overlap >= max(1, len(item_words) // 2):
                best_score = overlap
                best_item = item
        
        return best_item
```
### 9.2 Confidence Scorer
```python
# ai-pipeline/harvester/enrichment/confidence_scorer.py
from schemas.extraction import RawOrganizationData
from schemas.navigator_core import ClassificationPayload

def calculate_confidence(
    raw: RawOrganizationData,
    classification: ClassificationPayload,
) -> tuple[float, str, bool]:
    """
    Возвращает (score, explanation, works_with_elderly).
    score >= 0.85 + works_with_elderly=True → auto-approve (Smart Publish).
    """
    score = 0.0
    factors = []
    
    if raw.title:
        score += 0.10; factors.append("название")
    if raw.short_description or raw.full_description:
        score += 0.10; factors.append("описание")
    if raw.phones or raw.emails:
        score += 0.10; factors.append("контакты")
    if raw.addresses:
        score += 0.15; factors.append(f"{len(raw.addresses)} адрес(ов)")
    if raw.inn:
        score += 0.10; factors.append("ИНН")
    if raw.ogrn:
        score += 0.05; factors.append("ОГРН")
    if classification.thematic_category_codes:
        score += 0.10; factors.append(f"{len(classification.thematic_category_codes)} категорий")
    if classification.service_codes:
        score += 0.10; factors.append(f"{len(classification.service_codes)} услуг")
    if classification.organization_type_codes:
        score += 0.05; factors.append("тип определён")
    
    works_with_elderly = bool(raw.works_with_elderly_evidence)
    if works_with_elderly:
        score += 0.15; factors.append("работа с пожилыми подтверждена")
    
    return min(round(score, 4), 1.0), "; ".join(factors), works_with_elderly
```
### 9.3 Payload Builder
```python
# ai-pipeline/harvester/enrichment/payload_builder.py
from schemas.extraction import RawOrganizationData
from schemas.navigator_core import (
    OrganizationImportPayload, AiMetadata, AiDecision,
    ClassificationPayload, VenuePayload,
)
from enrichment.classifier import SeederClassifier
from enrichment.confidence_scorer import calculate_confidence
from enrichment.dadata_client import DadataClient
from strategies.regex_strategy import extract_contacts

class PayloadBuilder:
    def __init__(self, classifier: SeederClassifier, dadata: DadataClient):
        self.classifier = classifier
        self.dadata = dadata
    
    async def build(
        self,
        source_id: str,
        raw: RawOrganizationData,
        raw_html: str,
        source_url: str,
    ) -> OrganizationImportPayload:
        
        # 0. Regex-обогащение контактов (0 токенов)
        contacts = extract_contacts(raw_html)
        if contacts.phones and not raw.phones:
            raw.phones = contacts.phones
        if contacts.emails and not raw.emails:
            raw.emails = contacts.emails
        if contacts.inn and not raw.inn:
            raw.inn = contacts.inn
        if contacts.ogrn and not raw.ogrn:
            raw.ogrn = contacts.ogrn
        
        # 1. Классификация по сидерам
        classification = self.classifier.classify(raw)
        
        # 2. Confidence score
        score, explanation, elderly = calculate_confidence(raw, classification)
        
        # 3. Геокодирование через Dadata
        venues = []
        for i, addr in enumerate(raw.addresses[:3]):  # max 3 адреса
            geo = await self.dadata.geocode(addr)
            venues.append(VenuePayload(
                address_raw=addr,
                fias_id=geo.get("fias_id") if geo else None,
                geo_lat=geo.get("geo_lat") if geo else None,
                geo_lon=geo.get("geo_lon") if geo else None,
                is_headquarters=(i == 0),
            ))
        
        # 4. Decision
        decision = AiDecision.accepted if score >= 0.5 else AiDecision.rejected
        
        return OrganizationImportPayload(
            source_reference=f"orgweb_{source_id}",
            entity_type="Organization",
            title=raw.title,
            description=raw.full_description or raw.short_description or None,
            inn=raw.inn or None,
            ogrn=raw.ogrn or None,
            ai_metadata=AiMetadata(
                decision=decision,
                ai_confidence_score=score,
                works_with_elderly=elderly,
                ai_explanation=explanation,
                ai_source_trace={
                    "source_id": source_id,
                    "url": source_url,
                    "harvester_version": "1.0.0",
                    "extraction_method": "crawl4ai+deepseek",
                },
            ),
            classification=classification,
            venues=venues,
        )
```

***
## 10. Celery-задачи и оркестрация
```python
# ai-pipeline/harvester/workers/celery_app.py
from celery import Celery
from config.settings import get_settings

settings = get_settings()
app = Celery("harvester", broker=settings.redis_url, backend=settings.redis_url)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    timezone="Europe/Moscow",
    task_soft_time_limit=120,
    task_time_limit=180,
    worker_concurrency=4,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
```

```python
# ai-pipeline/harvester/workers/tasks.py
import asyncio
from workers.celery_app import app
from strategies.multi_page import MultiPageCrawler
from strategies.strategy_router import StrategyRouter
from enrichment.payload_builder import PayloadBuilder
from enrichment.classifier import SeederClassifier
from enrichment.dadata_client import DadataClient
from core_client.api import NavigatorCoreClient
from config.seeders import load_seeders
from config.settings import get_settings
from schemas.extraction import RawOrganizationData

settings = get_settings()

@app.task(bind=True, max_retries=3, default_retry_delay=60)
def crawl_and_enrich(self, source_data: dict):
    """
    Основная задача. Получает из Laravel:
    {"source_id": "uuid", "base_url": "...", "parse_profile_config": {...}}
    """
    try:
        return asyncio.run(_process(source_data))
    except Exception as exc:
        self.retry(exc=exc)

async def _process(source_data: dict) -> dict:
    source_id = source_data["source_id"]
    base_url = source_data["base_url"]
    config = source_data.get("parse_profile_config", {})
    
    router = StrategyRouter()
    crawler = MultiPageCrawler(router)
    seeders = load_seeders()
    classifier = SeederClassifier(seeders)
    dadata = DadataClient(settings.dadata_api_key, settings.dadata_secret_key)
    core = NavigatorCoreClient(settings.core_api_url, settings.core_api_token)
    builder = PayloadBuilder(classifier, dadata)
    
    # Краулинг
    raw_data = await crawler.crawl_organization(base_url, config)
    if "error" in raw_data:
        await core.update_source_status(source_id, "error", raw_data["error"])
        return {"status": "error", "source_id": source_id}
    
    raw = RawOrganizationData(**raw_data)
    
    # Обогащение + payload
    payload = await builder.build(source_id, raw, raw_data.get("_html", ""), base_url)
    
    # Отправка в Core
    response = await core.import_organizer(payload)
    await core.update_source_status(source_id, "completed")
    
    return {
        "status": "success",
        "source_id": source_id,
        "organizer_id": response.get("organizer_id"),
        "confidence": payload.ai_metadata.ai_confidence_score,
    }

@app.task
def process_batch(source_ids: list[str]):
    """Batch-обработка от Laravel: POST /harvest/run {sourceIds: [...]}"""
    core = NavigatorCoreClient(settings.core_api_url, settings.core_api_token)
    for sid in source_ids:
        data = asyncio.run(core.get_source(sid))
        crawl_and_enrich.delay(data)
```

***
## 11. Защита данных (staging, diff, immutability)
Harvester **никогда не записывает данные напрямую** в основные таблицы. Весь поток проходит через Core API, который реализует:[^1]

1. **Staging** — данные поступают в `staging_organization_updates` (JSON)
2. **Diff Analysis** — сравнение с текущими данными организации
3. **Immutability Rules** — поля, верифицированные через Dadata (`verified_by_dadata = true`), НЕ перезаписываются Harvester'ом
4. **Data Lineage** — `ai_source_trace` JSONB фиксирует source_id, URL, версию, метод экстракции
5. **Human-in-the-Loop** — организации с `ai_confidence_score < 0.85` попадают на ручную модерацию (`status = pending_review`)

Эта логика реализуется на стороне **Laravel Core** (endpoint `POST /api/internal/import/organizer`), а не в Python Harvester.[^2]

***
## 12. Расширяемость: Phase 2 (агрегаторы)
Архитектура Phase 1 заложена с учётом будущего расширения. Для Phase 2 потребуются:

| Компонент | Текущее | Добавить |
|---|---|---|
| `sources.kind` | `org_website` | +`registry_fpg`, `registry_sonko`, `platform_dobro` |
| `parseprofiles.crawl_strategy` | `list`, `sitemap` | +`paginated_list`, `open_data_csv` |
| Логика матчинга | Обогащение существующих | +`match_or_create` (ИНН/ОГРН → merge или propose) |
| Промпты | Единый базовый | +Полиморфные по типу источника/организации |

Структурных изменений в Harvester не потребуется — расширение через новые стратегии и промпты.

***
## 13. Пошаговый план внедрения
### Sprint 1 (Неделя 1–2): Скелет + первый краул
| # | Задача | Файлы | Часы |
|---|---|---|---|
| 1.1 | Создать `ai-pipeline/harvester/`, pyproject.toml, .env | `pyproject.toml`, `.env` | 2 |
| 1.2 | `config/settings.py`, `config/llm_config.py` | `config/` | 2 |
| 1.3 | Laravel: `ExportSeedersJson` artisan-команда | `backend/` | 3 |
| 1.4 | `config/seeders.py` — загрузка JSON-справочников | `config/seeders.py` | 2 |
| 1.5 | `schemas/extraction.py` + `schemas/navigator_core.py` | `schemas/` | 3 |
| 1.6 | `strategies/strategy_router.py` с LLM-стратегией | `strategies/` | 4 |
| 1.7 | `strategies/regex_strategy.py` | `strategies/` | 2 |
| 1.8 | `prompts/base_system_prompt.py` — stub с инъекцией сидеров | `prompts/` | 3 |
| 1.9 | `scripts/run_single_url.py` — CLI для отладки | `scripts/` | 2 |
| 1.10 | Тест: 5 реальных КЦСОН через CLI | — | 4 |

**DoD:** CLI принимает URL → Crawl4AI + DeepSeek → выводит `RawOrganizationData` в JSON.
### Sprint 2 (Неделя 3–4): Классификация + Core API
| # | Задача | Файлы | Часы |
|---|---|---|---|
| 2.1 | `enrichment/classifier.py` с реальными кодами сидеров | `enrichment/` | 6 |
| 2.2 | `enrichment/dadata_client.py` | `enrichment/` | 3 |
| 2.3 | `enrichment/confidence_scorer.py` | `enrichment/` | 3 |
| 2.4 | `enrichment/payload_builder.py` | `enrichment/` | 4 |
| 2.5 | `core_client/api.py` (POST import/organizer) | `core_client/` | 4 |
| 2.6 | End-to-end: URL → payload → Core API (staging) | — | 4 |
| 2.7 | Fixtures: HTML-снапшоты для unit-тестов | `tests/fixtures/` | 3 |

**DoD:** URL → полный pipeline → JSON в Core API staging.
### Sprint 3 (Неделя 5–6): Multi-page + CSS + Celery
| # | Задача | Файлы | Часы |
|---|---|---|---|
| 3.1 | `strategies/multi_page.py` | `strategies/` | 6 |
| 3.2 | Генерация CSS-шаблонов (3–5 типовых КЦСОН) | `schemas/css_templates/` | 4 |
| 3.3 | `strategies/css_strategy.py` | `strategies/` | 3 |
| 3.4 | Celery: `celery_app.py`, `tasks.py` | `workers/` | 4 |
| 3.5 | Docker + docker-compose | `Dockerfile` | 4 |
| 3.6 | Batch-тест: 50 организаций | — | 4 |

**DoD:** Celery-воркер обрабатывает batch из 50 URL. CSS-шаблоны работают без LLM-токенов.
### Sprint 4 (Неделя 7–8): Продакшен + первый проход
| # | Задача | Файлы | Часы |
|---|---|---|---|
| 4.1 | Structured logging (structlog) | — | 3 |
| 4.2 | Error handling, retry (tenacity) | — | 3 |
| 4.3 | Метрики: стоимость, success rate, время | — | 4 |
| 4.4 | Интеграция с Laravel Scheduler (POST /harvest/run) | — | 3 |
| 4.5 | Firecrawl Cloud fallback | — | 4 |
| 4.6 | **Первый полный проход: все org_website** | — | 8 |
| 4.7 | Анализ результатов, настройка порогов | — | 4 |

**DoD:** Все ~5 000 org_website обработаны, результаты в staging Core.

***
## 14. Оценка ресурсов
| Ресурс | Оценка |
|---|---|
| **Человекочасы** | ~120–140 ч (1 Python-разработчик, ~8 недель) |
| **DeepSeek API** | $8–15 за первый проход (10K страниц) |
| **Dadata API** | Бесплатный план (10K запросов/день) |
| **Firecrawl Cloud fallback** | $16/мес (Hobby, 3 000 кредитов) |
| **Инфраструктура** | VPS 2 vCPU / 4 GB RAM + Redis (~$15/мес) |
| **Итого monthly** | ~$30–45/мес + трудозатраты |

***
## 15. Инструкция для Cursor
При загрузке этого документа в Cursor как контекст, ключевые принципы:

1. **Pydantic-first** — все данные через Pydantic-модели. Никаких сырых `dict`.
2. **Коды из справочников** — LLM не генерирует коды. Только `classifier.py` маппит на коды из `seeders_data/*.json`. Реальные коды: `ThematicCategory` (7–29), `Service` (21–136), `OrganizationType` (65–140), `SpecialistProfile` (96–143), `OwnershipType` (152–167, исключая 151).
3. **Три уровня экстракции** — Regex → CSS → LLM. Переключение через `StrategyRouter`.
4. **DeepSeek через LiteLLM** — `provider="deepseek/deepseek-chat"`, env `DEEPSEEK_API_KEY`.
5. **ai_source_trace** — каждый payload содержит трассировку.
6. **Async-first** — весь I/O через asyncio. Celery для оркестрации.
7. **Immutability** — Harvester НЕ перезаписывает verified-данные. Только staging → diff → upsert через Core API.
8. **Промпты — отдельно** — папка `prompts/` содержит stub. Полиморфные промпты разрабатываются как отдельный workstream по `AI_Pipeline_Navigator_Plan.md`.
9. **Справочники из Laravel** — PHP-файлы сидеров (`backend/database/seeders/*Seeder.php`) → JSON → Python. Для понимания кодов читай PHP-сидеры.
10. **Путь проекта** — `ai-pipeline/harvester/`, на одном уровне с `backend/`.

---

## References

1. [AI_Pipeline_Navigator_Plan.md](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/80715158/ff0c3f26-b779-49db-873c-54fcf89da948/AI_Pipeline_Navigator_Plan.md?AWSAccessKeyId=ASIA2F3EMEYE6FJNTD3Q&Signature=enuPRJMWDG0pKH4xZoPulDEYXQE%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOH%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQD4CI07smNEvyLKpSxce%2Bc2cEyB%2FnSgaTK44lEuOIsS%2BAIgJvUW5XN0x1%2BbHJwq6exSQ6vuzsHc1Rs%2FkveD0Uq7vw8q%2FAQIqv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARABGgw2OTk3NTMzMDk3MDUiDEUbh4YfOkF9CiTa4irQBHwVuz1TSu0j8BSkHaltMmVFdeQXSORiKN5y4gYQfZuoVTFfzQd9Urk7DvFQlvVsYC%2FCWyYrXUioMcrUuhb5K6G2PCwyXUCg1pFLPzhYAeZTDg62UuJiFJUVhe89OpyuOy0xt4%2F8AhYiIb3LhqEEHyavswntZV0Oqfgo%2FeVWyaY4t4Mv5pK38fyi5oYMdtHb4JF%2BA1jKf42ASx2kiVukMU5Etg2qkr1jaC5dfEZMkMdaGX6f0TVPvLhLGxCIuOg3RSjc2wnvTjdLSGxLSX6y%2BgE7dzwaWCS1ce7iQnBQ0n%2B1yVhM1KC%2B6%2BfNFKUIDsKx8Tnp5Y9TWSlRVmN6dOg2sd1n4kS0ZNdt3tJHmDc%2BDSF%2B3gG0yXhu4NF85bjtHCvkcnyCJ3SYTZtCK9EApyCqX6Gt%2FTxpSoyNPnGbHuGTxNaF%2F6BpefgphUeqH1XKJZtmh1eJQX0u3vKdSJjsXUgOuFqrV40f26nk2VPGgxQoQpLIEhENsXjwfvVQ5LAosBVVOT%2FWZFlkQBUP44iNVQqccHObPWZN7K%2FpC%2F7OZXtx%2Bi9oqUi2sadi19S1Jmu9Vryq%2FRaPW2hEX3uHEpn8o2oLu9XWvjdNpLZFYWdYU%2FdOuGih7POY5A62p0MMZUeIqSCNTMSE1AStB%2FiWb7wr%2BhwL5hfT6RXuphufQTdLgIW2bRjV%2FG2KvWm7RQZK7vfvTLvjfaz%2FS8M7jdV9a4BRzTtoKDG4RuT4yqQP2f1pSHB9P8%2FCBQPciAf275z8SZHmW%2B%2FNJvUx8B%2FL%2FSZ9DJnoBhafIoswnt3lzAY6mAGsEbPMJ4UlyUAVo%2BPENTDD%2BPtuac%2BJ1IMzvGwYh8Ok%2BHS4A3JSYKzES0MYDM8frm0WCrnlrEqz7YVr8%2FcyKRwF8XTVxxVDOkLSOvAXjP51daA9NxI7YU73ls4Ey9S1jTD4ss7iWCCLMv2t%2FB8SFyLdLoAKHUGqmhHCE9PPoZrBZZZdzolNmRMKecO6CsBnf0q5h8%2Blp%2B6p0g%3D%3D&Expires=1771667464) - AI Pipeline , . -, CSS , -, .1 Harvester , - . LLM Agentic AI , , .2 . , -, , TITLE AI Pipeline Harv...

2. [Navigator_Core_Model_and_API.md](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/80715158/30265bf1-340a-4a60-b737-5dc60e74c6be/Navigator_Core_Model_and_API.md?AWSAccessKeyId=ASIA2F3EMEYE6FJNTD3Q&Signature=%2F7aUHMwM4VFzna1DmV1JJkR%2Fnuw%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOH%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQD4CI07smNEvyLKpSxce%2Bc2cEyB%2FnSgaTK44lEuOIsS%2BAIgJvUW5XN0x1%2BbHJwq6exSQ6vuzsHc1Rs%2FkveD0Uq7vw8q%2FAQIqv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARABGgw2OTk3NTMzMDk3MDUiDEUbh4YfOkF9CiTa4irQBHwVuz1TSu0j8BSkHaltMmVFdeQXSORiKN5y4gYQfZuoVTFfzQd9Urk7DvFQlvVsYC%2FCWyYrXUioMcrUuhb5K6G2PCwyXUCg1pFLPzhYAeZTDg62UuJiFJUVhe89OpyuOy0xt4%2F8AhYiIb3LhqEEHyavswntZV0Oqfgo%2FeVWyaY4t4Mv5pK38fyi5oYMdtHb4JF%2BA1jKf42ASx2kiVukMU5Etg2qkr1jaC5dfEZMkMdaGX6f0TVPvLhLGxCIuOg3RSjc2wnvTjdLSGxLSX6y%2BgE7dzwaWCS1ce7iQnBQ0n%2B1yVhM1KC%2B6%2BfNFKUIDsKx8Tnp5Y9TWSlRVmN6dOg2sd1n4kS0ZNdt3tJHmDc%2BDSF%2B3gG0yXhu4NF85bjtHCvkcnyCJ3SYTZtCK9EApyCqX6Gt%2FTxpSoyNPnGbHuGTxNaF%2F6BpefgphUeqH1XKJZtmh1eJQX0u3vKdSJjsXUgOuFqrV40f26nk2VPGgxQoQpLIEhENsXjwfvVQ5LAosBVVOT%2FWZFlkQBUP44iNVQqccHObPWZN7K%2FpC%2F7OZXtx%2Bi9oqUi2sadi19S1Jmu9Vryq%2FRaPW2hEX3uHEpn8o2oLu9XWvjdNpLZFYWdYU%2FdOuGih7POY5A62p0MMZUeIqSCNTMSE1AStB%2FiWb7wr%2BhwL5hfT6RXuphufQTdLgIW2bRjV%2FG2KvWm7RQZK7vfvTLvjfaz%2FS8M7jdV9a4BRzTtoKDG4RuT4yqQP2f1pSHB9P8%2FCBQPciAf275z8SZHmW%2B%2FNJvUx8B%2FL%2FSZ9DJnoBhafIoswnt3lzAY6mAGsEbPMJ4UlyUAVo%2BPENTDD%2BPtuac%2BJ1IMzvGwYh8Ok%2BHS4A3JSYKzES0MYDM8frm0WCrnlrEqz7YVr8%2FcyKRwF8XTVxxVDOkLSOvAXjP51daA9NxI7YU73ls4Ey9S1jTD4ss7iWCCLMv2t%2FB8SFyLdLoAKHUGqmhHCE9PPoZrBZZZdzolNmRMKecO6CsBnf0q5h8%2Blp%2B6p0g%3D%3D&Expires=1771667464) - . , TITLE API Navigator Core -

3. [GitHub - unclecode/crawl4ai: 🚀🤖 Crawl4AI: Open-source ...](https://github.com/unclecode/crawl4ai) - Limited slots. Crawl4AI turns the web into clean, LLM ready Markdown for RAG, agents, and data pipel...

4. [Deepseek - LiteLLM](https://docs.litellm.ai/docs/providers/deepseek) - Deepseek https://deepseek.com/ We support ALL Deepseek models, just set deepseek/ as a prefix when s...

5. [Extraction & Chunking Strategies API - Crawl4AI](https://docs.crawl4ai.com/api/strategies/) - All extraction strategies inherit from the base ExtractionStrategy class and implement two key metho...

6. [Quick Start - Crawl4AI Documentation (v0.8.x)](https://docs.crawl4ai.com/core/quickstart/) - Simple Data Extraction (CSS-based). Crawl4AI can also extract structured data (JSON) using CSS or XP...

7. [Master Crawl4AI Proxy Security & Authentication](https://www.crawl4.com/blog/master-crawl4ai-proxy-authentication-security-configuration) - Enabling stealth mode via the enable_stealth=True flag in BrowserConfig alters browser fingerprints,...

8. [Browser, Crawler & LLM Config](https://docs.crawl4ai.com/api/parameters/) - 🚀🤖 Crawl4AI, Open-source LLM-Friendly Web Crawler & Scraper

9. [Is Firecrawl Worth $16/Month in 2026? My Take](https://www.fahimai.com/ru/firecrawl) - Firecrawl pricing starts at free with 500 credits. The Hobby plan is $16/month with 3,000 credits. T...

10. [Self-hosting](https://docs.firecrawl.dev/contributing/self-host) - Self-hosting Firecrawl is particularly beneficial for organizations with stringent security policies...

11. [Deepseek API Pricing (Updated 2026) – All Models & Token Costs](https://pricepertoken.com/pricing-page/provider/deepseek) - Complete Deepseek API pricing guide for 2026. Compare all models with per-token costs, context lengt...

12. [Models & Pricing | DeepSeek API Docs](https://api-docs.deepseek.com/quick_start/pricing) - The prices listed below are in units of per 1M tokens. A token, the smallest unit of text that the m...

13. [DeepSeek API Pricing Calculator & Cost Guide (Feb 2026) - CostGoat](https://costgoat.com/pricing/deepseek-api) - Calculate DeepSeek API costs instantly. V3.2 pricing: $0.028-$0.28 input, $0.42 output per million t...

14. [OrganizationTypeSeeder.txt](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/80715158/f1bc1c2d-579e-4fa2-b16b-8a811d219095/OrganizationTypeSeeder.txt?AWSAccessKeyId=ASIA2F3EMEYE6FJNTD3Q&Signature=QoSbiJ11apner3kyYRX%2Bpvnb%2F5Q%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOH%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQD4CI07smNEvyLKpSxce%2Bc2cEyB%2FnSgaTK44lEuOIsS%2BAIgJvUW5XN0x1%2BbHJwq6exSQ6vuzsHc1Rs%2FkveD0Uq7vw8q%2FAQIqv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARABGgw2OTk3NTMzMDk3MDUiDEUbh4YfOkF9CiTa4irQBHwVuz1TSu0j8BSkHaltMmVFdeQXSORiKN5y4gYQfZuoVTFfzQd9Urk7DvFQlvVsYC%2FCWyYrXUioMcrUuhb5K6G2PCwyXUCg1pFLPzhYAeZTDg62UuJiFJUVhe89OpyuOy0xt4%2F8AhYiIb3LhqEEHyavswntZV0Oqfgo%2FeVWyaY4t4Mv5pK38fyi5oYMdtHb4JF%2BA1jKf42ASx2kiVukMU5Etg2qkr1jaC5dfEZMkMdaGX6f0TVPvLhLGxCIuOg3RSjc2wnvTjdLSGxLSX6y%2BgE7dzwaWCS1ce7iQnBQ0n%2B1yVhM1KC%2B6%2BfNFKUIDsKx8Tnp5Y9TWSlRVmN6dOg2sd1n4kS0ZNdt3tJHmDc%2BDSF%2B3gG0yXhu4NF85bjtHCvkcnyCJ3SYTZtCK9EApyCqX6Gt%2FTxpSoyNPnGbHuGTxNaF%2F6BpefgphUeqH1XKJZtmh1eJQX0u3vKdSJjsXUgOuFqrV40f26nk2VPGgxQoQpLIEhENsXjwfvVQ5LAosBVVOT%2FWZFlkQBUP44iNVQqccHObPWZN7K%2FpC%2F7OZXtx%2Bi9oqUi2sadi19S1Jmu9Vryq%2FRaPW2hEX3uHEpn8o2oLu9XWvjdNpLZFYWdYU%2FdOuGih7POY5A62p0MMZUeIqSCNTMSE1AStB%2FiWb7wr%2BhwL5hfT6RXuphufQTdLgIW2bRjV%2FG2KvWm7RQZK7vfvTLvjfaz%2FS8M7jdV9a4BRzTtoKDG4RuT4yqQP2f1pSHB9P8%2FCBQPciAf275z8SZHmW%2B%2FNJvUx8B%2FL%2FSZ9DJnoBhafIoswnt3lzAY6mAGsEbPMJ4UlyUAVo%2BPENTDD%2BPtuac%2BJ1IMzvGwYh8Ok%2BHS4A3JSYKzES0MYDM8frm0WCrnlrEqz7YVr8%2FcyKRwF8XTVxxVDOkLSOvAXjP51daA9NxI7YU73ls4Ey9S1jTD4ss7iWCCLMv2t%2FB8SFyLdLoAKHUGqmhHCE9PPoZrBZZZdzolNmRMKecO6CsBnf0q5h8%2Blp%2B6p0g%3D%3D&Expires=1771667464) - <?php

namespace Database\Seeders;

use App\Models\OrganizationType;
use Illuminate\Database\Console...

15. [ThematicCategorySeeder.txt](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/80715158/c866e5b2-64a1-4681-82e4-b912076d83ca/ThematicCategorySeeder.txt?AWSAccessKeyId=ASIA2F3EMEYE6FJNTD3Q&Signature=mXc8aUsu6NrfEswBQXeSKQg8eVg%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOH%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQD4CI07smNEvyLKpSxce%2Bc2cEyB%2FnSgaTK44lEuOIsS%2BAIgJvUW5XN0x1%2BbHJwq6exSQ6vuzsHc1Rs%2FkveD0Uq7vw8q%2FAQIqv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARABGgw2OTk3NTMzMDk3MDUiDEUbh4YfOkF9CiTa4irQBHwVuz1TSu0j8BSkHaltMmVFdeQXSORiKN5y4gYQfZuoVTFfzQd9Urk7DvFQlvVsYC%2FCWyYrXUioMcrUuhb5K6G2PCwyXUCg1pFLPzhYAeZTDg62UuJiFJUVhe89OpyuOy0xt4%2F8AhYiIb3LhqEEHyavswntZV0Oqfgo%2FeVWyaY4t4Mv5pK38fyi5oYMdtHb4JF%2BA1jKf42ASx2kiVukMU5Etg2qkr1jaC5dfEZMkMdaGX6f0TVPvLhLGxCIuOg3RSjc2wnvTjdLSGxLSX6y%2BgE7dzwaWCS1ce7iQnBQ0n%2B1yVhM1KC%2B6%2BfNFKUIDsKx8Tnp5Y9TWSlRVmN6dOg2sd1n4kS0ZNdt3tJHmDc%2BDSF%2B3gG0yXhu4NF85bjtHCvkcnyCJ3SYTZtCK9EApyCqX6Gt%2FTxpSoyNPnGbHuGTxNaF%2F6BpefgphUeqH1XKJZtmh1eJQX0u3vKdSJjsXUgOuFqrV40f26nk2VPGgxQoQpLIEhENsXjwfvVQ5LAosBVVOT%2FWZFlkQBUP44iNVQqccHObPWZN7K%2FpC%2F7OZXtx%2Bi9oqUi2sadi19S1Jmu9Vryq%2FRaPW2hEX3uHEpn8o2oLu9XWvjdNpLZFYWdYU%2FdOuGih7POY5A62p0MMZUeIqSCNTMSE1AStB%2FiWb7wr%2BhwL5hfT6RXuphufQTdLgIW2bRjV%2FG2KvWm7RQZK7vfvTLvjfaz%2FS8M7jdV9a4BRzTtoKDG4RuT4yqQP2f1pSHB9P8%2FCBQPciAf275z8SZHmW%2B%2FNJvUx8B%2FL%2FSZ9DJnoBhafIoswnt3lzAY6mAGsEbPMJ4UlyUAVo%2BPENTDD%2BPtuac%2BJ1IMzvGwYh8Ok%2BHS4A3JSYKzES0MYDM8frm0WCrnlrEqz7YVr8%2FcyKRwF8XTVxxVDOkLSOvAXjP51daA9NxI7YU73ls4Ey9S1jTD4ss7iWCCLMv2t%2FB8SFyLdLoAKHUGqmhHCE9PPoZrBZZZdzolNmRMKecO6CsBnf0q5h8%2Blp%2B6p0g%3D%3D&Expires=1771667464) - <?php

namespace Database\Seeders;

use App\Models\ThematicCategory;
use Illuminate\Database\Console...

16. [ServiceSeeder.txt](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/80715158/fb690eff-ea94-45e9-b431-f97e95df9c2b/ServiceSeeder.txt?AWSAccessKeyId=ASIA2F3EMEYE6FJNTD3Q&Signature=Lch4XQkE3jfopXqGjinJS1cpYEs%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOH%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQD4CI07smNEvyLKpSxce%2Bc2cEyB%2FnSgaTK44lEuOIsS%2BAIgJvUW5XN0x1%2BbHJwq6exSQ6vuzsHc1Rs%2FkveD0Uq7vw8q%2FAQIqv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARABGgw2OTk3NTMzMDk3MDUiDEUbh4YfOkF9CiTa4irQBHwVuz1TSu0j8BSkHaltMmVFdeQXSORiKN5y4gYQfZuoVTFfzQd9Urk7DvFQlvVsYC%2FCWyYrXUioMcrUuhb5K6G2PCwyXUCg1pFLPzhYAeZTDg62UuJiFJUVhe89OpyuOy0xt4%2F8AhYiIb3LhqEEHyavswntZV0Oqfgo%2FeVWyaY4t4Mv5pK38fyi5oYMdtHb4JF%2BA1jKf42ASx2kiVukMU5Etg2qkr1jaC5dfEZMkMdaGX6f0TVPvLhLGxCIuOg3RSjc2wnvTjdLSGxLSX6y%2BgE7dzwaWCS1ce7iQnBQ0n%2B1yVhM1KC%2B6%2BfNFKUIDsKx8Tnp5Y9TWSlRVmN6dOg2sd1n4kS0ZNdt3tJHmDc%2BDSF%2B3gG0yXhu4NF85bjtHCvkcnyCJ3SYTZtCK9EApyCqX6Gt%2FTxpSoyNPnGbHuGTxNaF%2F6BpefgphUeqH1XKJZtmh1eJQX0u3vKdSJjsXUgOuFqrV40f26nk2VPGgxQoQpLIEhENsXjwfvVQ5LAosBVVOT%2FWZFlkQBUP44iNVQqccHObPWZN7K%2FpC%2F7OZXtx%2Bi9oqUi2sadi19S1Jmu9Vryq%2FRaPW2hEX3uHEpn8o2oLu9XWvjdNpLZFYWdYU%2FdOuGih7POY5A62p0MMZUeIqSCNTMSE1AStB%2FiWb7wr%2BhwL5hfT6RXuphufQTdLgIW2bRjV%2FG2KvWm7RQZK7vfvTLvjfaz%2FS8M7jdV9a4BRzTtoKDG4RuT4yqQP2f1pSHB9P8%2FCBQPciAf275z8SZHmW%2B%2FNJvUx8B%2FL%2FSZ9DJnoBhafIoswnt3lzAY6mAGsEbPMJ4UlyUAVo%2BPENTDD%2BPtuac%2BJ1IMzvGwYh8Ok%2BHS4A3JSYKzES0MYDM8frm0WCrnlrEqz7YVr8%2FcyKRwF8XTVxxVDOkLSOvAXjP51daA9NxI7YU73ls4Ey9S1jTD4ss7iWCCLMv2t%2FB8SFyLdLoAKHUGqmhHCE9PPoZrBZZZdzolNmRMKecO6CsBnf0q5h8%2Blp%2B6p0g%3D%3D&Expires=1771667464) - <?php

namespace Database\Seeders;

use App\Models\Service;
use Illuminate\Database\Console\Seeds\Wi...

17. [SpecialistProfileSeeder.txt](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/80715158/8849a304-1771-459b-94f9-8ee614cb89ba/SpecialistProfileSeeder.txt?AWSAccessKeyId=ASIA2F3EMEYE6FJNTD3Q&Signature=RUlZ3KGw4OYh8QUbpk4JvXBmBnE%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOH%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQD4CI07smNEvyLKpSxce%2Bc2cEyB%2FnSgaTK44lEuOIsS%2BAIgJvUW5XN0x1%2BbHJwq6exSQ6vuzsHc1Rs%2FkveD0Uq7vw8q%2FAQIqv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARABGgw2OTk3NTMzMDk3MDUiDEUbh4YfOkF9CiTa4irQBHwVuz1TSu0j8BSkHaltMmVFdeQXSORiKN5y4gYQfZuoVTFfzQd9Urk7DvFQlvVsYC%2FCWyYrXUioMcrUuhb5K6G2PCwyXUCg1pFLPzhYAeZTDg62UuJiFJUVhe89OpyuOy0xt4%2F8AhYiIb3LhqEEHyavswntZV0Oqfgo%2FeVWyaY4t4Mv5pK38fyi5oYMdtHb4JF%2BA1jKf42ASx2kiVukMU5Etg2qkr1jaC5dfEZMkMdaGX6f0TVPvLhLGxCIuOg3RSjc2wnvTjdLSGxLSX6y%2BgE7dzwaWCS1ce7iQnBQ0n%2B1yVhM1KC%2B6%2BfNFKUIDsKx8Tnp5Y9TWSlRVmN6dOg2sd1n4kS0ZNdt3tJHmDc%2BDSF%2B3gG0yXhu4NF85bjtHCvkcnyCJ3SYTZtCK9EApyCqX6Gt%2FTxpSoyNPnGbHuGTxNaF%2F6BpefgphUeqH1XKJZtmh1eJQX0u3vKdSJjsXUgOuFqrV40f26nk2VPGgxQoQpLIEhENsXjwfvVQ5LAosBVVOT%2FWZFlkQBUP44iNVQqccHObPWZN7K%2FpC%2F7OZXtx%2Bi9oqUi2sadi19S1Jmu9Vryq%2FRaPW2hEX3uHEpn8o2oLu9XWvjdNpLZFYWdYU%2FdOuGih7POY5A62p0MMZUeIqSCNTMSE1AStB%2FiWb7wr%2BhwL5hfT6RXuphufQTdLgIW2bRjV%2FG2KvWm7RQZK7vfvTLvjfaz%2FS8M7jdV9a4BRzTtoKDG4RuT4yqQP2f1pSHB9P8%2FCBQPciAf275z8SZHmW%2B%2FNJvUx8B%2FL%2FSZ9DJnoBhafIoswnt3lzAY6mAGsEbPMJ4UlyUAVo%2BPENTDD%2BPtuac%2BJ1IMzvGwYh8Ok%2BHS4A3JSYKzES0MYDM8frm0WCrnlrEqz7YVr8%2FcyKRwF8XTVxxVDOkLSOvAXjP51daA9NxI7YU73ls4Ey9S1jTD4ss7iWCCLMv2t%2FB8SFyLdLoAKHUGqmhHCE9PPoZrBZZZdzolNmRMKecO6CsBnf0q5h8%2Blp%2B6p0g%3D%3D&Expires=1771667464) - <?php

namespace Database\Seeders;

use App\Models\SpecialistProfile;
use Illuminate\Database\Consol...

18. [OwnershipTypeSeeder.txt](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/80715158/57b51655-d502-4ecd-9b25-059d3d48131b/OwnershipTypeSeeder.txt?AWSAccessKeyId=ASIA2F3EMEYE6FJNTD3Q&Signature=wAbJZkYYE8MArU9LIycxvaIIP14%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOH%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQD4CI07smNEvyLKpSxce%2Bc2cEyB%2FnSgaTK44lEuOIsS%2BAIgJvUW5XN0x1%2BbHJwq6exSQ6vuzsHc1Rs%2FkveD0Uq7vw8q%2FAQIqv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARABGgw2OTk3NTMzMDk3MDUiDEUbh4YfOkF9CiTa4irQBHwVuz1TSu0j8BSkHaltMmVFdeQXSORiKN5y4gYQfZuoVTFfzQd9Urk7DvFQlvVsYC%2FCWyYrXUioMcrUuhb5K6G2PCwyXUCg1pFLPzhYAeZTDg62UuJiFJUVhe89OpyuOy0xt4%2F8AhYiIb3LhqEEHyavswntZV0Oqfgo%2FeVWyaY4t4Mv5pK38fyi5oYMdtHb4JF%2BA1jKf42ASx2kiVukMU5Etg2qkr1jaC5dfEZMkMdaGX6f0TVPvLhLGxCIuOg3RSjc2wnvTjdLSGxLSX6y%2BgE7dzwaWCS1ce7iQnBQ0n%2B1yVhM1KC%2B6%2BfNFKUIDsKx8Tnp5Y9TWSlRVmN6dOg2sd1n4kS0ZNdt3tJHmDc%2BDSF%2B3gG0yXhu4NF85bjtHCvkcnyCJ3SYTZtCK9EApyCqX6Gt%2FTxpSoyNPnGbHuGTxNaF%2F6BpefgphUeqH1XKJZtmh1eJQX0u3vKdSJjsXUgOuFqrV40f26nk2VPGgxQoQpLIEhENsXjwfvVQ5LAosBVVOT%2FWZFlkQBUP44iNVQqccHObPWZN7K%2FpC%2F7OZXtx%2Bi9oqUi2sadi19S1Jmu9Vryq%2FRaPW2hEX3uHEpn8o2oLu9XWvjdNpLZFYWdYU%2FdOuGih7POY5A62p0MMZUeIqSCNTMSE1AStB%2FiWb7wr%2BhwL5hfT6RXuphufQTdLgIW2bRjV%2FG2KvWm7RQZK7vfvTLvjfaz%2FS8M7jdV9a4BRzTtoKDG4RuT4yqQP2f1pSHB9P8%2FCBQPciAf275z8SZHmW%2B%2FNJvUx8B%2FL%2FSZ9DJnoBhafIoswnt3lzAY6mAGsEbPMJ4UlyUAVo%2BPENTDD%2BPtuac%2BJ1IMzvGwYh8Ok%2BHS4A3JSYKzES0MYDM8frm0WCrnlrEqz7YVr8%2FcyKRwF8XTVxxVDOkLSOvAXjP51daA9NxI7YU73ls4Ey9S1jTD4ss7iWCCLMv2t%2FB8SFyLdLoAKHUGqmhHCE9PPoZrBZZZdzolNmRMKecO6CsBnf0q5h8%2Blp%2B6p0g%3D%3D&Expires=1771667464) - <?php

namespace Database\Seeders;

use App\Models\OwnershipType;
use Illuminate\Database\Console\Se...

