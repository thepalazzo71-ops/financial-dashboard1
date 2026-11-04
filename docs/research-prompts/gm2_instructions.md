TASK (second attempt): estimate/find the latest-fiscal-year gross margin for each company in your input file. These are Asia/Pacific small caps for which a first search pass found no gross-profit line. Use ONLY WebSearch (WebFetch is blocked). At most 2 searches per company. Today is 2026-10-29.

Different tactics than the first pass - the problem was that search summaries showed revenue but not the gross-profit line:
1. Search for the MARGIN or COST RATIO directly, in the local language, e.g.
   - Japan: "<社名 or code> 売上総利益率 2026", "粗利率", "売上原価率", "原価率" (gross margin = 1 - 売上原価率)
   - Korea: "<회사명> 매출총이익률", "매출원가율", "매출총이익 2025" (gross margin = 1 - 매출원가율)
   - Hong Kong/China: "<name> 毛利率 2025", "gross profit margin 2025 annual results"
   - SG/AU/NZ: "<name> gross margin FY2026", "gross profit margin results".
2. Accept ANY of: a stated gross margin %, a cost-of-sales ratio (then gm = 1 - ratio), gross profit and revenue figures, or revenue and cost of sales. The year must be the latest FY (or TTM) and consolidated if consolidated is available; say so. Margin percentages stated by the company itself (results presentation, IR page, annual report) are best; aggregator pages (Yahoo Japan, Kabutan, Minkabu, IR BANK, Buffett Code, Naver/FnGuide, Paasa, StockAnalysis, MarketScreener, Simply Wall St) are acceptable if a year is shown. Record which: source_type = company_statement | annual_report | results_announcement | aggregator_margin | aggregator_statement.
3. If you cannot find it, do NOT leave it empty: still return the business classification below so a peer-median estimate can be made.

For EVERY company also return (whether or not you found the margin):
 - industry_group: exactly one of: software_it_services | internet_media_games | semiconductors_electronic_components | electronic_equipment_hardware | machinery_equipment | auto_parts_transport_equipment | chemicals_materials | metals_steel_mining | food_beverage_agri | consumer_goods_apparel | retail_stores | wholesale_trading_distribution | restaurants_leisure_hospitality | construction_engineering | real_estate_property_services | transport_logistics_shipping | healthcare_pharma_biotech | medical_devices_equipment | staffing_education_business_services | telecom_utilities_energy | packaging_paper_printing | building_materials | other
 - business: <=12 words describing what it does (from what you saw; if you could not identify the company, say 'unidentified').
 Use ONE search to identify the business if the name alone is not enough - merge it with the margin search where possible.

Rules: verify the stock code matches (beware same-name companies); gm must be between -0.5 and 1.0; never guess a margin. Put helper files only in a folder named after your output file (e.g. gm2_r01_a_work/).

OUTPUT: write your output file with Python (json.dump, ensure_ascii=False) as
{ticker: {"status": "ok|not_found", "gm": float|null, "fiscal_year": str, "basis": "consolidated|non-consolidated|unknown", "how": "gm_stated|cost_ratio|gp_and_revenue|revenue_and_cogs", "source_url": str, "source_type": str, "industry_group": str, "business": str, "notes": str}}
Rewrite after every 5 companies. Never write entries for companies you did not research. Final reply: 2 lines max (counts ok / not_found / not reached).
