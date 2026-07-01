"""JS generation helpers for chat-mode extract tools.

Reuses JS extraction logic from extract.py as module-level constants,
providing safe selector escaping and custom field-mapping JS generation.
"""

import json


def _safe_selector(sel: str) -> str:
    """Escape single quotes in a CSS selector for safe JS string interpolation."""
    return sel.replace("'", "\\'")


def _build_selector_js(selector: str) -> str:
    """Generate JS to extract items under a custom CSS selector.

    Each matched element returns {text, href} (first <a> href).
    """
    safe = _safe_selector(selector)
    return f"""() => {{
    const clean = (v) => (v || '').replace(/\\s+/g, ' ').trim();
    const items = Array.from(document.querySelectorAll('{safe}'));
    return items.filter(el => {{
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }}).map(el => ({{
        text: clean(el.textContent || ''),
        href: el.querySelector('a') ? el.querySelector('a').getAttribute('href') || '' : ''
    }}));
}}"""


def _build_field_extraction_js(selector: str, fields: dict) -> str:
    """Generate JS to extract items with custom field mappings.

    Rules:
      - ``"key": "h3"`` → ``el.querySelector('h3')?.textContent?.trim() || ''``
      - ``"key": "@attr"`` → ``el.getAttribute('attr') || ''``
    """
    safe = _safe_selector(selector)
    field_entries = []
    for key, expr in fields.items():
        if expr.startswith("@"):
            attr = _safe_selector(expr[1:])
            field_entries.append(
                f"    {json.dumps(key)}: el.getAttribute('{attr}') || ''"
            )
        else:
            sub_sel = _safe_selector(expr)
            field_entries.append(
                f"    {json.dumps(key)}: (el.querySelector('{sub_sel}')?.textContent?.trim() || '')"
            )
    fields_js = ",\n".join(field_entries)
    return f"""() => {{
    const clean = (v) => (v || '').replace(/\\s+/g, ' ').trim();
    const items = Array.from(document.querySelectorAll('{safe}'));
    return items.filter(el => {{
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }}).map(el => ({{
{fields_js}
    }}));
}}"""


def _build_table_selector_js(selector: str) -> str:
    """Generate JS to extract a table inside a specific container.

    Uses the same logic as EXTRACT_TABLE_JS but scoped to
    ``document.querySelector(selector)``.
    """
    safe = _safe_selector(selector)
    return f"""() => {{
    const clean = (v) => (v || '').replace(/\\s+/g, ' ').trim();
    const visible = (el) => {{
        if (!el) return false;
        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    }};
    const unique = (arr) => arr.filter((v, i, a) => v && a.indexOf(v) === i);
    const root = document.querySelector('{safe}');
    if (!root) return null;
    const cleanHeaderText = (el) => {{
        const text = clean(el.innerText || el.textContent || '');
        return text.replace(/\\s{{2,}}/g, ' ').trim();
    }};
    const cleanCellText = (el) => clean(el.innerText || el.textContent || '');
    const headers = unique(Array.from(root.querySelectorAll(
        '.vxe-header--column, .vxe-table--header .vxe-cell, ' +
        '.el-table__header-wrapper th, .el-table__fixed-header-wrapper th, ' +
        '.ant-table-thead th, thead th, [role="columnheader"], th'
    )).filter(visible).map(c => cleanHeaderText(c)).filter(Boolean));
    const rows = Array.from(root.querySelectorAll(
        '.vxe-body--row, .el-table__body-wrapper tbody tr, ' +
        '.el-table__row, .ant-table-row, [role="row"]'
    )).filter(visible).map(row => {{
        const cells = Array.from(row.querySelectorAll(
            '.vxe-body--column, .el-table__cell, .ant-table-cell, ' +
            '[role="gridcell"], [role="cell"], td'
        )).map(c => cleanCellText(c)).filter(Boolean);
        if (cells.length > 1) return cells;
        return clean(row.innerText || row.textContent || '')
            .split(/\\s{{2,}}|\\t+/).map(clean).filter(Boolean);
    }}).filter(r => r.some(Boolean) && r.join(' ') !== headers.join(' '));
    const seen = new Set();
    const deduped = rows.filter(r => {{
        const key = r.join('\\x00');
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    }});
    if (deduped.length > 0) {{
        const width = Math.max(headers.length, ...deduped.map(r => r.length));
        return {{
            headers: headers.length ? headers : Array.from(
                {{length: width}}, (_, i) => 'col_' + (i + 1)
            ),
            rows: deduped
        }};
    }}
    return null;
}}"""


def _build_details_selector_js(selector: str) -> str:
    """Generate JS to extract key-value details inside a specific container.

    Uses the same logic as EXTRACT_DETAILS_JS but scoped to
    ``document.querySelector(selector)``.
    """
    safe = _safe_selector(selector)
    return f"""() => {{
    const clean = (v) => (v || '').replace(/\\s+/g, ' ').trim();
    const container = document.querySelector('{safe}');
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
    const items = Array.from(container.querySelectorAll('li, .attr, [class*="attr"]'))
        .filter(el => {{ const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }});
    if (pairs.length === 0 && items.length > 0) {{
        items.forEach(item => {{
            const text = clean(item.textContent || '');
            const colonIdx = text.indexOf(':');
            if (colonIdx > 0) {{
                pairs.push({{ label: clean(text.substring(0, colonIdx)), value: clean(text.substring(colonIdx + 1)) }});
            }} else {{
                pairs.push({{ label: '', value: text }});
            }}
        }});
    }}
    if (pairs.length === 0) {{
        const dtElements = container.querySelectorAll('dt');
        const ddElements = container.querySelectorAll('dd');
        const maxLen = Math.min(dtElements.length, ddElements.length);
        for (let i = 0; i < maxLen; i++) {{
            pairs.push({{ label: clean(dtElements[i].textContent || ''), value: clean(ddElements[i].textContent || '') }});
        }}
    }}
    return {{ text: clean(container.textContent || ''), details: pairs }};
}}"""
