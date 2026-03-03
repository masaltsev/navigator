# Presidential Grants Fund - Data Source Analysis

**Date**: 2026-02-25  
**Scope**: Analysis of Presidential Grants Fund (Фонд президентских грантов) open data portal  
**Source URLs**: 
- Open Data Page: https://xn--80afcdbalict6afooklqi5o.xn--p1ai/public/open-data
- Projects Catalog: https://xn--80afcdbalict6afooklqi5o.xn--p1ai/public/application/cards

---

## Executive Summary

The Presidential Grants Fund provides open data about projects that have requested financing from 2017 onwards. The data is available both as downloadable datasets and through individual project detail pages with rich information.

---

## 1. Open Data Downloads

### 1.1 Projects Dataset (Main Dataset)
- **Description**: Information about projects that requested financing from the Presidential Grants Fund (from 2017)
- **Title (RU)**: "Сведения о проектах, на реализацию которых запрошено финансирование у Фонда президентских грантов (с 2017 года)"
- **Download URL**: `https://файлы.президентскиегранты.рф/81cf9ab5-07f9-4272-a058-ec578b4e4c61`
- **Format**: XLSX (Excel)
- **Last Updated**: 22.01.2026
- **Status**: File server returned 503 error during testing (may be temporary)

### 1.2 Projects Data Passport
- **Description**: Metadata document describing the projects dataset structure
- **Title (RU)**: "Паспорт набора данных о проектах, на реализацию которых запрошено финансирование у Фонда президентских грантов (с 2017 года)"
- **Download URL**: `https://файлы.президентскиегранты.рф/bc5ab5a7-2408-4ead-b18e-89fa8ac361cf`
- **Format**: PDF
- **Purpose**: Documentation of data structure, field definitions, update frequency

### 1.3 Co-financing Dataset
- **Description**: Data on co-financing support for non-profit organizations in Russian regions from 2021
- **Title (RU)**: "Данные о софинансировании поддержки некоммерческих организаций в субъектах Российской Федерации с 2021 года"
- **Download URL**: `https://файлы.президентскиегранты.рф/c7ffab4b-183d-4440-9b63-55360eade254`
- **Format**: Data file (likely XLSX)

### 1.4 Co-financing Data Passport
- **Download URL**: `https://файлы.президентскиегранты.рф/ff9de896-b32f-4e88-98e5-4008bb5cc85f`
- **Format**: PDF

---

## 2. Project Detail Pages

### 2.1 URL Structure
**Pattern**: `/public/application/item?id={UUID}`

**Example URLs**:
- `https://xn--80afcdbalict6afooklqi5o.xn--p1ai/public/application/item?id=b888e910-a634-4ad8-8614-2c607ae2ff68`
- `https://xn--80afcdbalict6afooklqi5o.xn--p1ai/public/application/item?id=8511b57b-3270-4446-92c6-a211533c73a2`

Each project has a unique UUID identifier used in the URL query parameter.

### 2.2 Available Data Fields on Detail Pages

#### Project Metadata (winner-info__list)
1. **Конкурс** (Contest) - e.g., "Второй конкурс 2026"
2. **Грантовое направление** (Grant Direction) - e.g., "Охрана здоровья граждан, пропаганда здорового образа жизни"
3. **Номер заявки** (Application Number) - e.g., "26-2-007316"
4. **Дата подачи** (Submission Date) - e.g., "25.02.2026"
5. **Запрашиваемая сумма** (Requested Amount) - in Rubles
6. **Cофинансирование** (Co-financing) - in Rubles
7. **Общая сумма расходов на реализацию проекта** (Total Project Expenses) - in Rubles
8. **Сроки реализации** (Implementation Period) - Start and End dates
9. **Организация** (Organization) - Full organization name
10. **ИНН** (Tax ID) - Organization tax identification number
11. **ОГРН** (State Registration Number) - Organization state registration number

#### Project Content Sections (winner__details-box)
1. **Краткое описание** (Brief Description) - Short project summary
2. **Цель** (Goal) - Project objectives (structured as numbered list)
3. **Задачи** (Tasks) - Project tasks (structured as numbered list)
4. **Обоснование социальной значимости** (Social Significance Justification) - Detailed explanation of project's social importance
5. **География проекта** (Project Geography) - Geographic scope and locations
6. **Целевые группы** (Target Groups) - Beneficiary groups (structured as numbered list)

#### Contact Information (winner__details-contacts)
1. **Address** - Full postal address with region, city, street
2. **Веб-сайт** (Website) - Organization website URL
   - **Note**: Field exists but often shows "нет" (none) - many organizations don't have websites listed
3. **Yandex Map Integration** - Address is geocoded and displayed on Yandex Maps
   - Map data includes: `{"address":"...", "yandexApiKey":"..."}`

---

## 3. Additional Data Sources Found

### 3.1 Annual Reports (2017-2024)
Available in PDF format, file sizes ranging from 4.7 MB to 37.37 MB:
- 2024: `https://файлы.президентскиегранты.рф/b786f235-4154-49cf-8f48-ed7788ad4c14` (9.1 MB)
- 2023: `https://файлы.президентскиегранты.рф/f56b31c6-da2f-408d-8353-2d945f82da55` (6.7 MB)
- 2022-2017: [Additional URLs available]

### 3.2 Project Evaluation Reports
Reports on assessment of project results by year:
- 2024 evaluation: `https://файлы.президентскиегранты.рф/0a1ce2a0-8cc5-46d5-ae04-b2b3773fad78`
- 2023 evaluation: `https://файлы.президентскиегранты.рф/61bed005-f74a-4dad-8584-6945b7734605`
- [Previous years available]

### 3.3 API Endpoints Detected
- `/public/api/v1/file/get-document?filename={UUID}.pdf` - For document downloads
- `/public/api/v1/file/get-image?fileName={UUID}.ico` - For image assets

---

## 4. Data Fields NOT in XLSX (Available Only on Web)

Based on analysis of project detail pages, the following rich data fields are likely **NOT available** in the downloadable XLSX file but **ARE available** on individual project web pages:

### 4.1 Extended Project Content
1. **Краткое описание** - Full brief description (likely truncated in XLSX)
2. **Цель** - Detailed project goals with full text
3. **Задачи** - Complete task list with descriptions
4. **Обоснование социальной значимости** - Full justification text (often multi-paragraph)
5. **География проекта** - Detailed geographic description
6. **Целевые группы** - Detailed target group descriptions

### 4.2 Organization Details
1. **Website URL** - Organization website (when available)
2. **Full Postal Address** - Complete address with formatting
3. **Geocoded Location** - Latitude/longitude for mapping

### 4.3 Financial Breakdown
- Visual representation of funding structure
- Percentage breakdowns of co-financing vs. grant amounts

### 4.4 Implementation Timeline
- Structured date ranges with better formatting
- Visual timeline representation

---

## 5. Data Extraction Strategy Recommendations

### 5.1 For Bulk Data Collection
**Primary Method**: Download the XLSX file from the open data portal
- **URL**: `https://файлы.президентскиегранты.рф/81cf9ab5-07f9-4272-a058-ec578b4e4c61`
- **Pros**: Single file with all projects, structured data, updated regularly
- **Cons**: May not include full text descriptions, missing website URLs, requires handling Excel format

### 5.2 For Enriched Data
**Supplementary Method**: Web scraping of individual project pages
- **URL Pattern**: `/public/application/item?id={UUID}`
- **Pros**: Rich text content, full descriptions, website URLs when available
- **Cons**: Requires HTTP requests per project, rate limiting considerations

### 5.3 Hybrid Approach (Recommended)
1. **Start with XLSX**: Download and parse the main dataset for structured metadata
2. **Extract UUIDs**: Get project IDs from XLSX or catalog page
3. **Enrich via Web**: Scrape individual project pages for:
   - Full text descriptions
   - Organization websites
   - Detailed geographic information
   - Complete justification texts
4. **Cache Results**: Store enriched data to avoid repeated requests

---

## 6. Technical Considerations

### 6.1 Character Encoding
- Pages use HTML entity encoding for Cyrillic text (e.g., `&#x41F;&#x440;&#x43E;&#x435;&#x43A;&#x442;&#x44B;`)
- Need to decode entities when scraping

### 6.2 SSL/TLS Issues
- The file server subdomain (`файлы.президентскиегранты.рф`) has SSL certificate issues
- May need to use `-k` flag with curl or disable SSL verification
- Production implementation should investigate proper certificate handling

### 6.3 Rate Limiting
- No explicit rate limiting observed during testing
- Recommend implementing polite scraping with delays (1-2 seconds between requests)
- User-Agent header should be set to identify the scraper

### 6.4 File Server Availability
- The file server returned 503 errors during testing
- May indicate:
  - Temporary downtime
  - Load balancing issues
  - Access restrictions
- Implement retry logic with exponential backoff

---

## 7. Sample Data Structure

### Example Project (ID: b888e910-a634-4ad8-8614-2c607ae2ff68)

```json
{
  "id": "b888e910-a634-4ad8-8614-2c607ae2ff68",
  "contest": "Второй конкурс 2026",
  "grant_direction": "Охрана здоровья граждан, пропаганда здорового образа жизни",
  "application_number": "26-2-007316",
  "submission_date": "2026-02-25",
  "requested_amount": 980059.00,
  "cofinancing": 0.00,
  "total_expenses": 980059.00,
  "implementation_period": {
    "start": "2026-07-01",
    "end": "2027-03-30"
  },
  "organization": {
    "name": "МЕСТНАЯ ОБЩЕСТВЕННАЯ ОРГАНИЗАЦИЯ ТЕРРИТОРИАЛЬНОЕ ОБЩЕСТВЕННОЕ САМОУПРАВЛЕНИЕ \"ЛУКОМОРЬЕ\" СЕЛА СМОРОДИНО ЯКОВЛЕВСКОГО ГОРОДСКОГО ОКРУГА БЕЛГОРОДСКОЙ ОБЛАСТИ",
    "inn": "3100017116",
    "ogrn": "1233100005555",
    "address": "309065, БЕЛГОРОДСКАЯ ОБЛАСТЬ, М.О. ЯКОВЛЕВСКИЙ, С СМОРОДИНО, УЛ НАБЕРЕЖНАЯ, Д. 4",
    "website": null
  },
  "project": {
    "brief_description": "Проект \"Сельский спорт: сила традиций и здоровье нации\" направлен на охрану здоровья подрастающего поколения и развитие хоккея в селе...",
    "goal": ["Сохранить и укрепить здоровье подрастающего поколения...", "Создать доступные условия для занятий хоккеем..."],
    "tasks": ["Открытие обустроенной спортивной площадки...", "Популяризировать занятия спортом...", ...],
    "social_significance": "Согласно статистике России, растет уровень заболеваний среди детей и подростков...",
    "geography": "4 населённых пункта Смородинской территории: с. Смородино, х. Каменский, с. Непхаево, х. Глушинский",
    "target_groups": ["Дети и подростки Смородинской территории (до 18 лет...)"]
  }
}
```

---

## 8. Next Steps for Implementation

1. **Download Data Passport PDF**: Review field definitions and data dictionary
2. **Implement XLSX Parser**: Parse the main dataset file
3. **Build Project Catalog Scraper**: Extract project UUIDs from catalog page
4. **Implement Detail Page Scraper**: Extract enriched data from individual pages
5. **Create Data Pipeline**:
   - Download XLSX regularly (weekly/monthly based on update frequency)
   - Identify new/updated projects
   - Scrape detail pages for enrichment
   - Store in database with proper indexing
6. **Monitoring**: Track file server availability and implement alerting

---

## 9. Conclusion

The Presidential Grants Fund provides a comprehensive open data resource with:
- **Structured Data**: XLSX downloads for bulk access
- **Rich Content**: Individual project pages with detailed descriptions
- **Regular Updates**: Dataset updated as of January 22, 2026
- **Additional Resources**: Annual reports and evaluation documents

**Recommended Approach**: Hybrid strategy combining XLSX parsing for metadata with selective web scraping for enriched content, particularly organization websites and full project descriptions.

**Main Challenge**: File server availability (503 errors observed) - requires robust retry logic and error handling.
