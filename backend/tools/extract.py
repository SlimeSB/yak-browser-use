"""Page extraction tools for browser-use pipelines.

These tools require browser/CDP access to extract data from web pages.
Migrated to ToolContext — functions receive ``ctx: ToolContext`` instead
of raw ``cdp_helpers``.
"""
from __future__ import annotations

from typing import Any

from engine.ops import ToolContext
from utils.logging import get_logger

logger = get_logger(__name__)

# ── Client-side JS for table extraction ──

EXTRACT_TABLE_JS = """() => {
    const clean = (v) => (v || '').replace(/\\s+/g, ' ').trim();
    const visible = (el) => {
        if (!el) return false;
        const node = el;
        return !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
    };
    const unique = (arr) => arr.filter((v, i, a) => v && a.indexOf(v) === i);

    const cleanHeaderText = (el) => {
        const text = clean(el.innerText || el.textContent || '');
        return text.replace(/\\s{2,}/g, ' ').trim();
    };

    const cleanCellText = (el) => {
        return clean(el.innerText || el.textContent || '');
    };

    const roots = Array.from(document.querySelectorAll(
        '.vxe-grid, .vxe-table, .el-table, .ant-table-wrapper, ' +
        '[role="grid"], [role="table"], table, [class*="table"]'
    ));

    for (const root of roots) {
        if (!visible(root)) continue;

        const headers = unique(Array.from(root.querySelectorAll(
            '.vxe-header--column, .vxe-table--header .vxe-cell, ' +
            '.el-table__header-wrapper th, .el-table__fixed-header-wrapper th, ' +
            '.ant-table-thead th, thead th, [role="columnheader"], th'
        )).filter(visible).map(c => cleanHeaderText(c)).filter(Boolean));

        const rows = Array.from(root.querySelectorAll(
            '.vxe-body--row, .el-table__body-wrapper tbody tr, ' +
            '.el-table__row, .ant-table-row, [role="row"]'
        )).filter(visible).map(row => {
            const cells = Array.from(row.querySelectorAll(
                '.vxe-body--column, .el-table__cell, .ant-table-cell, ' +
                '[role="gridcell"], [role="cell"], td'
            )).map(c => cleanCellText(c)).filter(Boolean);
            if (cells.length > 1) return cells;
            return clean(row.innerText || row.textContent || '')
                .split(/\\s{2,}|\\t+/).map(clean).filter(Boolean);
        }).filter(r => r.some(Boolean) && r.join(' ') !== headers.join(' '));

        const seen = new Set();
        const deduped = rows.filter(r => {
            const key = r.join('\\x00');
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });

        if (deduped.length > 0) {
            const width = Math.max(headers.length, ...deduped.map(r => r.length));
            return {
                headers: headers.length ? headers : Array.from(
                    {length: width}, (_, i) => 'col_' + (i + 1)
                ),
                rows: deduped
            };
        }
    }
    return null;
}"""

EXTRACT_LIST_JS = """() => {
    const clean = (v) => (v || '').replace(/\\s+/g, ' ').trim();
    const visible = (el) => {
        if (!el) return false;
        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    };

    // Try common list structures: ul > li, div[role="listitem"], etc.
    const selectors = [
        'li', '[role="listitem"]', '.item', '.list-item', '[class*="result-item"]',
        '[data-component-type="s-search-result"]', '.s-result-item'
    ];

    for (const sel of selectors) {
        const items = Array.from(document.querySelectorAll(sel)).filter(visible);
        if (items.length > 1) {
            return items.map(item => {
                const link = item.querySelector('a[href]');
                const title = item.querySelector('h2, h3, [class*="title"], [class*="heading"]');
                return {
                    href: link ? link.getAttribute('href') || '' : '',
                    title: clean(title ? title.textContent || '' : ''),
                    text: clean(item.textContent || '')
                };
            }).filter(item => item.title || item.href);
        }
    }
    return [];
}"""

EXTRACT_DETAILS_JS = """() => {
    const clean = (v) => (v || '').replace(/\\s+/g, ' ').trim();
    const visible = (el) => {
        if (!el) return false;
        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    };

    // Extract structured key-value pairs from detail sections
    const detailSelectors = [
        '#detailBullets_feature_div', '#productDetails_feature_div',
        '.detail-bullet-list', '[class*="detail"]', '.attribute-list',
        '.product-details', '#productDetails_techSpec_section',
        '#productDetails_detailBullets_sections_rows',
        'table[class*="detail"]', '[class*="spec"]'
    ];

    const result = { text: clean(document.body.innerText || ''), details: [] };

    for (const sel of detailSelectors) {
        const section = document.querySelector(sel);
        if (!section || !visible(section)) continue;

        // Try table rows first
        const rows = section.querySelectorAll('tr');
        if (rows.length > 0) {
            const pairs = Array.from(rows).map(tr => {
                const cells = tr.querySelectorAll('th, td');
                if (cells.length >= 2) {
                    return { label: clean(cells[0].textContent || ''), value: clean(cells[1].textContent || '') };
                }
                return null;
            }).filter(Boolean);
            result.details = pairs;
            break;
        }

        // Try list items with label: value pattern
        const items = Array.from(section.querySelectorAll('li, .attr, [class*="attr"]'))
            .filter(visible);
        if (items.length > 0) {
            const pairs = items.map(item => {
                const text = clean(item.textContent || '');
                const colonIdx = text.indexOf(':');
                if (colonIdx > 0) {
                    return { label: clean(text.substring(0, colonIdx)), value: clean(text.substring(colonIdx + 1)) };
                }
                return { label: '', value: text };
            }).filter(p => p.label || p.value);
            result.details = pairs;
            break;
        }
    }

    // Try extracting definition lists (dl > dt/dd)
    if (result.details.length === 0) {
        const dl = document.querySelector('dl');
        if (dl && visible(dl)) {
            const dts = dl.querySelectorAll('dt');
            const dds = dl.querySelectorAll('dd');
            const pairs = [];
            const maxLen = Math.min(dts.length, dds.length);
            for (let i = 0; i < maxLen; i++) {
                pairs.push({ label: clean(dts[i].textContent || ''), value: clean(dds[i].textContent || '') });
            }
            result.details = pairs;
        }
    }

    return result;
}"""


async def extract_table(ctx: ToolContext, params: dict) -> dict:
    """Extract a table (headers + rows) from the current page.

    Uses client-side JS to locate visible tables rendered by common
    frameworks (Vue Element UI, Ant Design, plain HTML tables).

    Parameters in **params:
        poll_seconds (float): Seconds to wait before extracting (default: 2).
        selector (str): Optional CSS selector to target a specific table.
    """
    poll_seconds = float(params.get("poll_seconds", 2.0))
    if poll_seconds > 0:
        await ctx.wait(poll_seconds)

    logger.debug("extract_table: target=%s, poll_seconds=%s", params.get("selector", "auto"), poll_seconds)

    result = await ctx.evaluate(EXTRACT_TABLE_JS)
    if result and result.get("rows"):
        await ctx.save_json(result, "table.json")
        return {"ok": True, "rows": len(result["rows"]), "cols": len(result.get("headers", []))}
    else:
        await ctx.save_json({"headers": [], "rows": []}, "table.json")
        return {"ok": True, "rows": 0, "message": "no table found on page"}


async def extract_list(ctx: ToolContext, params: dict) -> dict:
    """Extract a list of items from the current page.

    Looks for common list structures (li, role="listitem", result items).

    Parameters in **params:
        poll_seconds (float): Seconds to wait before extracting (default: 1).
        selector (str): Optional custom CSS selector for list items.
        attribute (str): Optional data attribute to extract from each item.
    """
    poll_seconds = float(params.get("poll_seconds", 1.0))
    if poll_seconds > 0:
        await ctx.wait(poll_seconds)

    logger.debug("extract_list: target=%s, poll_seconds=%s", params.get("selector", "auto"), poll_seconds)

    if params.get("selector"):
        custom_js = f"""() => {{
            const clean = (v) => (v || '').replace(/\\s+/g, ' ').trim();
            const items = Array.from(document.querySelectorAll('{params["selector"]}'));
            const attr = '{params.get("attribute", "")}';
            return items.filter(el => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }}).map(el => ({{
                text: clean(el.textContent || ''),
                href: el.querySelector('a') ? el.querySelector('a').getAttribute('href') || '' : '',
                attr: attr ? el.getAttribute(attr) || '' : ''
            }}));
        }}"""
        result = await ctx.evaluate(custom_js)
    else:
        result = await ctx.evaluate(EXTRACT_LIST_JS)

    await ctx.save_json(result or [], "list.json")
    count = len(result) if result else 0
    return {"ok": True, "count": count}


async def extract_details(ctx: ToolContext, params: dict) -> dict:
    """Extract structured details (key-value pairs) from the current page.

    Scans for detail sections, attribute lists, spec tables, and definition lists.

    Parameters in **params:
        poll_seconds (float): Seconds to wait before extracting (default: 1).
        selector (str): Optional custom CSS selector for the detail container.
    """
    poll_seconds = float(params.get("poll_seconds", 1.0))
    if poll_seconds > 0:
        await ctx.wait(poll_seconds)

    logger.debug("extract_details: target=%s, poll_seconds=%s", params.get("selector", "auto"), poll_seconds)

    if params.get("selector"):
        custom_js = f"""() => {{
            const clean = (v) => (v || '').replace(/\\s+/g, ' ').trim();
            const container = document.querySelector('{params["selector"]}');
            if (!container) return {{ text: '', details: [] }};
            const pairs = [];
            const rows = container.querySelectorAll('tr');
            if (rows.length > 0) {{
                Array.from(rows).forEach(tr => {{
                    const cells = tr.querySelectorAll('th, td');
                    if (cells.length >= 2) {{
                        pairs.push({{ label: clean(cells[0].textContent || ''), value: clean(cells[1].textContent || '') }});
                    }}
                }});
            }}
            return {{ text: clean(container.textContent || ''), details: pairs }};
        }}"""
        result = await ctx.evaluate(custom_js)
    else:
        result = await ctx.evaluate(EXTRACT_DETAILS_JS)

    await ctx.save_json(result, "details.json")
    detail_count = len(result.get("details", [])) if result else 0
    return {"ok": True, "count": detail_count}
