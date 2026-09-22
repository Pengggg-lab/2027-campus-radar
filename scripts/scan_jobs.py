#!/usr/bin/env python3
"""Check official recruitment pages for evidence of 2027 campus recruiting."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Browser, async_playwright


TZ_CN = timezone(timedelta(hours=8))
TARGET_YEAR = 2027
CAMPUS_WORDS = ("校园招聘", "校招", "秋招", "秋季招聘", "应届生招聘", "毕业生招聘", "高校毕业生", "应届毕业生", "网申")
TARGET_RE = re.compile(r"(2027\s*届|2027\s*年度|2027\s*(?:校园|秋季|秋招|校招)|27\s*届)", re.I)
CAMPUS_RE = re.compile("|".join(map(re.escape, CAMPUS_WORDS)), re.I)
DATE_FULL_RE = re.compile(r"(?P<y>20\d{2})\s*(?:年|[-./])\s*(?P<m>\d{1,2})\s*(?:月|[-./])\s*(?P<d>\d{1,2})\s*日?")
DATE_MD_RE = re.compile(r"(?<!\d)(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日")
DYNAMIC_DOMAINS = (
    "iguopin.com", "zhiye.com", "hotjob.cn", "zhaopin.com", "51job.com", "mokahr.com",
    "hcmcloud.ciecc.com.cn", "job.crtc-hr.com", "zhaopin.cnbm.com.cn", "zhaopin.sgcc.com.cn",
    "zhaopin.cnpc.com.cn", "job.sinopec.com", "campus.cec.com.cn", "app.mokahr.com",
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
STATUS_LABELS = {
    "today": "今日更新",
    "released": "已发现 2027 校招",
    "possible": "有校招入口，年份待核实",
    "not_found": "暂未发现 2027 校招",
    "error": "访问异常，待核实",
    "not_checked": "待扫描",
}
STATUS_RANK = {"not_checked": 0, "error": 1, "not_found": 2, "possible": 3, "released": 4, "today": 5}


def clean_text(value: str | None, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:limit]


def parse_dates(text: str, today: date, max_age_days: int = 210) -> list[date]:
    found: set[date] = set()
    for match in DATE_FULL_RE.finditer(text):
        try:
            found.add(date(int(match.group("y")), int(match.group("m")), int(match.group("d"))))
        except ValueError:
            pass
    for match in DATE_MD_RE.finditer(text):
        try:
            candidate = date(today.year, int(match.group("m")), int(match.group("d")))
            if candidate > today + timedelta(days=7):
                candidate = date(today.year - 1, candidate.month, candidate.day)
            found.add(candidate)
        except ValueError:
            pass
    lower = today - timedelta(days=max_age_days)
    upper = today + timedelta(days=7)
    return sorted(d for d in found if lower <= d <= upper)


def target_recruitment_window(text: str, today: date) -> tuple[bool, str | None]:
    """Require the target graduation year and recruitment words to be close together."""
    project_exclude = re.compile(
        r"(项目|计划|采购|招标|资金|检修|考试|申报|课题|工程|活动|会议|报告|政策|标准|建设|实施|数据库|系统|预算|公开|工作要点)"
    )
    job_words = re.compile(r"(招聘|投递|岗位|职位|管培生|工程师|研究员|专员|经理|本科|硕士|博士|实习生)")
    for match in TARGET_RE.finditer(text):
        before = text[max(0, match.start() - 120): match.start()]
        after = text[match.end(): match.end() + 180]
        window = before + match.group(0) + after
        if re.search(r"(2026\s*[-至~]\s*2027|2027\s*[-至~]\s*2028)", window):
            continue
        if not CAMPUS_RE.search(window):
            if "届" not in match.group(0) or not job_words.search(after[:140]):
                continue
        # Reject the common "2027年度 + 项目/资金/采购" business-document pattern.
        if not CAMPUS_RE.search(after[:55]) and project_exclude.search(after[:45]):
            continue
        return True, clean_text(window, 360)
    return False, None


def today_recruitment_evidence(text: str, today: date) -> tuple[bool, str | None]:
    today_pattern = re.compile(
        rf"(?:{today.year}\s*(?:年|[-./])\s*0?{today.month}\s*(?:月|[-./])\s*0?{today.day}|0?{today.month}\s*月\s*0?{today.day}\s*日)"
    )
    lines = [clean_text(line, 500) for line in text.splitlines()]
    lines = [line for line in lines if line]
    for index, line in enumerate(lines):
        if not today_pattern.search(line):
            continue
        context = line
        if len(line) < 45:
            context = " ".join(lines[max(0, index - 1): min(len(lines), index + 2)])
        window_target_hit, _ = target_recruitment_window(context, today)
        if CAMPUS_RE.search(context) or window_target_hit:
            return True, clean_text(context, 360)
    return False, None


def extract_page(html: str, final_url: str, page_title: str, today: date) -> dict[str, Any]:
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\n{2,}", "\n", soup.get_text("\n", strip=True))
    lines = [clean_text(line, 360) for line in soup.get_text("\n", strip=True).splitlines()]
    lines = [line for line in lines if len(line) >= 2]

    has_campus = bool(CAMPUS_RE.search(text))
    target_hit, target_evidence = target_recruitment_window(text, today)
    today_hit, today_evidence = today_recruitment_evidence(text, today)
    dates = parse_dates(text, today)
    latest_date = dates[-1] if dates else None

    meta_dates: list[date] = []
    for selector in (
        'meta[property="article:published_time"]', 'meta[name="publishdate"]',
        'meta[name="pubdate"]', 'meta[name="date"]', 'meta[itemprop="datePublished"]',
    ):
        node = soup.select_one(selector)
        if node and node.get("content"):
            meta_dates.extend(parse_dates(str(node["content"]), today))
    if meta_dates:
        latest_date = max(meta_dates + ([latest_date] if latest_date else []))

    scored_lines: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        score = 0
        if TARGET_RE.search(line):
            score += 100
        if CAMPUS_RE.search(line):
            score += 55
        if parse_dates(line, today):
            score += 18
        if score:
            context = " ".join(lines[max(0, index - 1): min(len(lines), index + 2)])
            scored_lines.append((score, clean_text(context, 360)))
    evidence = max(scored_lines, key=lambda item: item[0])[1] if scored_lines else clean_text(text, 260)
    if target_evidence:
        evidence = target_evidence
    if today_hit and today_evidence:
        evidence = today_evidence

    if today_hit:
        status = "today"
    elif target_hit:
        status = "released"
    elif has_campus:
        status = "possible"
    else:
        status = "not_found"

    related: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        label = clean_text(anchor.get_text(" ", strip=True), 90)
        href = urljoin(final_url, str(anchor.get("href")))
        if not href.startswith(("http://", "https://")) or href in seen_urls:
            continue
        haystack = f"{label} {href}"
        if not (TARGET_RE.search(haystack) or CAMPUS_RE.search(haystack) or re.search(r"job|position|zhiwei|campus|recruit", haystack, re.I)):
            continue
        if label in {"校园招聘", "招聘", "首页", "更多"} and len(related) > 0:
            continue
        seen_urls.add(href)
        related.append({"label": label or "招聘信息", "url": href})
        if len(related) >= 10:
            break

    return {
        "status": status,
        "todayUpdate": status == "today",
        "evidence": evidence,
        "evidenceDate": latest_date.isoformat() if latest_date else None,
        "pageTitle": clean_text(page_title, 160),
        "finalUrl": final_url,
        "relatedLinks": related,
        "subsidiaryHint": any(term in text for term in ("子公司", "成员公司", "所属单位", "所属企业", "分公司", "下属企业")),
    }


def scan_urls(item: dict[str, Any], url_field: str) -> list[str]:
    if url_field == "official":
        values = (item.get("officialUrl"), item.get("campusUrl"))
    elif url_field == "campus":
        values = (item.get("campusUrl"), item.get("officialUrl"))
    else:
        values = (item.get("campusUrl"), item.get("officialUrl"))
    return list(dict.fromkeys(url for url in values if url))


async def fetch_http(client: httpx.AsyncClient, item: dict[str, Any], url_field: str = "primary") -> dict[str, Any]:
    urls = scan_urls(item, url_field)
    if not urls:
        return {"ok": False, "error": "名单中缺少官网链接", "url": None}
    errors: list[str] = []
    for url in urls:
        try:
            response = await client.get(url, follow_redirects=True, timeout=20)
            if response.status_code < 400:
                return {
                    "ok": True,
                    "html": response.text[:1_500_000],
                    "finalUrl": str(response.url),
                    "pageTitle": "",
                    "httpStatus": response.status_code,
                    "error": None,
                    "url": url,
                }
            errors.append(f"{url}: HTTP {response.status_code}")
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:120]}")
    return {"ok": False, "error": "; ".join(errors)[:380], "url": urls[0]}


async def fetch_browser(browser: Browser, item: dict[str, Any], url_field: str = "primary") -> dict[str, Any]:
    urls = scan_urls(item, url_field)
    if not urls:
        return {"ok": False, "error": "名单中缺少官网链接", "url": None}
    context = await browser.new_context(
        locale="zh-CN",
        viewport={"width": 1440, "height": 1000},
        ignore_https_errors=True,
        user_agent=HEADERS["User-Agent"],
    )
    page = await context.new_page()

    async def block_heavy(route: Any) -> None:
        if route.request.resource_type in {"image", "media", "font"}:
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", block_heavy)
    errors: list[str] = []
    try:
        for url in urls:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=6000)
                except Exception:
                    pass
                await page.wait_for_timeout(1400)
                html = await page.content()
                return {
                    "ok": True,
                    "html": html[:1_500_000],
                    "finalUrl": page.url,
                    "pageTitle": await page.title(),
                    "httpStatus": 200,
                    "error": None,
                    "url": url,
                }
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:100]}")
        return {"ok": False, "error": "; ".join(errors)[:380], "url": urls[0]}
    finally:
        await context.close()


def needs_browser(item: dict[str, Any], http_result: dict[str, Any] | None, extracted: dict[str, Any] | None, url_field: str = "primary") -> bool:
    if not scan_urls(item, url_field):
        return False
    if not http_result or not http_result.get("ok") or not extracted:
        return True
    if extracted["status"] in {"today", "released"} and extracted.get("evidenceDate"):
        return False
    domain = urlparse((scan_urls(item, url_field) or [""])[0]).netloc.lower()
    if any(known in domain for known in DYNAMIC_DOMAINS):
        return True
    html = http_result.get("html", "").lower()
    shell_markers = ('id="app"', "id='app'", "__next_data__", "window.__", "vue", "react")
    return any(marker in html for marker in shell_markers)


def choose_result(http_result: dict[str, Any] | None, browser_result: dict[str, Any] | None, today: date) -> dict[str, Any]:
    candidates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for source, result in (("官网直连", http_result), ("浏览器渲染", browser_result)):
        if result and result.get("ok"):
            extracted = extract_page(result.get("html", ""), result.get("finalUrl") or result.get("url") or "", result.get("pageTitle", ""), today)
            candidates.append((source, result, extracted))
    if not candidates:
        return {"ok": False, "error": (browser_result or http_result or {}).get("error") or "无法访问"}
    source, result, extracted = max(candidates, key=lambda row: (STATUS_RANK[row[2]["status"]], row[0] == "浏览器渲染"))
    extracted["checkSource"] = source
    extracted["httpStatus"] = result.get("httpStatus")
    return {"ok": True, **extracted}


async def scan(args: argparse.Namespace) -> dict[str, Any]:
    source_path = args.input
    data = json.loads(source_path.read_text(encoding="utf-8"))
    companies = data.get("companies", [])
    if args.only:
        wanted = set(args.only)
        companies = [item for item in companies if item["id"] in wanted or item["name"] in wanted]
    if args.statuses:
        allowed = set(args.statuses)
        companies = [item for item in companies if item.get("status", "not_checked") in allowed]
    if args.limit:
        companies = companies[: args.limit]

    today = date.today()
    sem_http = asyncio.Semaphore(18)
    async with httpx.AsyncClient(headers=HEADERS, verify=False, follow_redirects=True) as client:
        async def limited_http(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
            async with sem_http:
                result = await fetch_http(client, item, args.url_field)
                extracted = extract_page(result.get("html", ""), result.get("finalUrl") or result.get("url") or "", "", today) if result.get("ok") else None
                return result, extracted
        http_rows = await asyncio.gather(*(limited_http(item) for item in companies))

    browser_jobs: list[tuple[int, dict[str, Any]]] = []
    for index, (item, (http_result, extracted)) in enumerate(zip(companies, http_rows)):
        if args.browser == "all" or (args.browser == "auto" and needs_browser(item, http_result, extracted, args.url_field)):
            browser_jobs.append((index, item))

    browser_rows: dict[int, dict[str, Any]] = {}
    if browser_jobs and args.browser != "off":
        executable = args.browser_path or os.environ.get("PLAYWRIGHT_BROWSER_PATH")
        launch_options: dict[str, Any] = {"headless": True}
        if executable:
            launch_options["executable_path"] = executable
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(**launch_options)
            sem_browser = asyncio.Semaphore(args.concurrency)
            async def limited_browser(index: int, item: dict[str, Any]) -> tuple[int, dict[str, Any]]:
                async with sem_browser:
                    return index, await fetch_browser(browser, item, args.url_field)
            results = await asyncio.gather(*(limited_browser(index, item) for index, item in browser_jobs))
            browser_rows = dict(results)
            await browser.close()

    checked_at = datetime.now(TZ_CN).isoformat(timespec="seconds")
    for index, (item, (http_result, _)) in enumerate(zip(companies, http_rows)):
        browser_result = browser_rows.get(index)
        result = choose_result(http_result, browser_result, today)
        check_error = None
        old_status = item.get("status", "not_checked")
        if result.get("ok") and args.keep_stronger and STATUS_RANK.get(result["status"], 0) <= STATUS_RANK.get(old_status, 0):
            item["lastChecked"] = checked_at
            if not item.get("evidence") and result.get("evidence"):
                item["evidence"] = result.get("evidence")
            print(f"[{index + 1}/{len(companies)}] {item['name']}: kept {old_status} (official pass {result['status']})", flush=True)
            continue
        if result.get("ok"):
            item.update({
                "status": result["status"],
                "statusLabel": STATUS_LABELS[result["status"]],
                "todayUpdate": result["todayUpdate"],
                "evidence": result.get("evidence"),
                "evidenceDate": result.get("evidenceDate"),
                "pageTitle": result.get("pageTitle"),
                "finalUrl": result.get("finalUrl"),
                "relatedLinks": result.get("relatedLinks", []),
                "subsidiaryHint": bool(result.get("subsidiaryHint")),
                "lastChecked": checked_at,
                "checkError": None,
                "checkSource": result.get("checkSource"),
                "httpStatus": result.get("httpStatus"),
                "previousStatus": None,
                "stale": False,
            })
        else:
            if args.keep_stronger:
                item["lastChecked"] = checked_at
                print(f"[{index + 1}/{len(companies)}] {item['name']}: kept {old_status} (official pass failed)", flush=True)
                continue
            check_error = result.get("error") or "访问失败"
            previous = item.get("status")
            if previous in {"today", "released", "possible", "not_found"}:
                effective_previous = "released" if previous == "today" else previous
                item.update({
                    "status": effective_previous,
                    "statusLabel": f"{STATUS_LABELS[effective_previous]}（今日未验证）",
                    "todayUpdate": False,
                    "lastChecked": checked_at,
                    "checkError": check_error,
                    "previousStatus": previous,
                    "stale": True,
                    "finalUrl": item.get("finalUrl") or http_result.get("finalUrl"),
                })
            else:
                item.update({
                    "status": "error",
                    "statusLabel": STATUS_LABELS["error"],
                    "todayUpdate": False,
                    "lastChecked": checked_at,
                    "checkError": check_error,
                    "previousStatus": None,
                    "stale": False,
                    "finalUrl": http_result.get("finalUrl") or item.get("finalUrl"),
                })
        print(f"[{index + 1}/{len(companies)}] {item['name']}: {item['status']} {check_error or ''}", flush=True)

    if args.limit or args.only or args.statuses:
        existing = {item["id"]: item for item in data.get("companies", [])}
        existing.update({item["id"]: item for item in companies})
        data["companies"] = [existing[item["id"]] for item in data.get("companies", [])]
    else:
        data["companies"] = companies

    counts = Counter(item.get("status", "not_checked") for item in data["companies"])
    data.setdefault("meta", {})["scannedAt"] = checked_at
    data["meta"]["stats"] = {key: counts.get(key, 0) for key in STATUS_LABELS}
    data["meta"]["browserChecks"] = len(browser_jobs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(args.output)
    print("stats", dict(data["meta"]["stats"]), file=sys.stderr)
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("site/data/companies.json"))
    parser.add_argument("--output", type=Path, default=Path("site/data/companies.json"))
    parser.add_argument("--browser", choices=("auto", "all", "off"), default="auto")
    parser.add_argument("--browser-path", default=None)
    parser.add_argument("--url-field", choices=("primary", "official", "campus"), default="primary")
    parser.add_argument("--statuses", nargs="*")
    parser.add_argument("--keep-stronger", action="store_true")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only", nargs="*")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(scan(parse_args()))
