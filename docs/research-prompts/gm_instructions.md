TASK: find the latest-fiscal-year consolidated GROSS MARGIN for each company in your input file (Asia/Pacific small/mid caps). Use ONLY WebSearch (WebFetch is blocked). At most 2 searches per company; most should need 1. Today is 2026-10-27.

Gross margin = gross profit / revenue = (revenue - cost of sales) / revenue, for the latest full fiscal year (FY2025 or FY ending in 2026; if the latest annual is older than ~15 months use TTM and say so), consolidated.

Search tips (one well-aimed query usually suffices):
- Japan (4-digit code): query like "<code> <Japanese or English name> 売上総利益 売上高 2025" — Kabutan/Minkabu/Yahoo Japan/IR BANK/株探/バフェット・コード pages show 売上高 and 売上総利益 (粗利).
- South Korea (6-digit code, drop the leading 'A'): "<company Korean name or code> 매출총이익 매출액 2025" — Naver/Comp.fnguide/Paasa/StockAnalysis.
- Hong Kong: "<name> <code> gross profit revenue 2025 annual results" (毛利 / 收入) — HKEX announcements, AAStocks, StockAnalysis.
- Singapore/Australia/NZ: "<name> gross profit revenue FY2025" — SGX/ASX announcements, StockAnalysis, MarketScreener.

Rules:
- Use only figures where BOTH the same-year revenue and the gross profit (or cost of sales) are visible in the source; compute gm yourself. Do not use a pre-computed 'gross margin %' you cannot tie to those lines.
- Companies with no cost-of-sales / gross-profit concept (banks, insurers, brokers, lessors, many Japanese/Korean service, shipping, construction or real-estate firms that report expenses by nature, holding companies) -> status 'no_gross_profit_line', gm null.
- If not found within 2 searches -> status 'not_found', gm null. Never guess; never copy another company's figures (check the stock code).
- source_type: annual_report | results_announcement | filing_data_page (company IR/exchange filing tables) | aggregator_statement (third-party pages showing the revenue and gross-profit lines).
- Sanity check: gm must be between -0.5 and 1.0; if the result looks odd (e.g. >0.9 for a manufacturer) re-check or mark not_found.

OUTPUT: write the output file named in your instructions with Python (json.dump, ensure_ascii=False) as
{ticker: {"status": "ok|no_gross_profit_line|not_found", "gm": float|null, "fiscal_year": str, "currency": str, "revenue": float|null, "gross_profit": float|null, "source_url": str, "source_label": str, "source_type": str, "notes": str}}
Rewrite the file after every 5 companies so nothing is lost. If you run out of search budget, stop and write what you have (do NOT write placeholder entries for companies you did not research). Final reply: 2 lines max (counts ok / no_gross_profit_line / not_found / not reached).

Housekeeping: if you write helper scripts or temp files, put them ONLY in a folder named after your output file (e.g. gm_r12_a_work/), never a generic shared name - other agents run in parallel in the same directory.
