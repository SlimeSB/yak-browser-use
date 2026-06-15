window.simplifyDom = (function () {
  'use strict';

  var MAX_ELEMENTS = 50;

  function isVisible(el) {
    if (!el || el.offsetParent === null) return null;
    var rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return null;
    if (rect.bottom < 0 || rect.top > window.innerHeight) return null;
    if (rect.right < 0 || rect.left > window.innerWidth) return null;
    var style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return null;
    if (parseFloat(style.opacity) === 0) return null;
    return rect;
  }

  function buildSelector(el) {
    if (el.id) return '#' + CSS.escape(el.id);
    var tag = el.tagName.toLowerCase();
    var parts = [tag];
    if (el.className && typeof el.className === 'string') {
      var classes = el.className.trim().split(/\s+/).filter(function (c) { return c.length > 0; });
      if (classes.length > 0) {
        parts.push('.' + classes.map(function (c) { return CSS.escape(c); }).join('.'));
      }
    }
    var name = el.getAttribute('name');
    if (name) parts.push('[name="' + name.replace(/"/g, '\\"') + '"]');
    var type = el.getAttribute('type');
    if (type) parts.push('[type="' + type.replace(/"/g, '\\"') + '"]');
    return parts.join('');
  }

  function getText(el, maxLen) {
    maxLen = maxLen || 60;
    var text = (el.textContent || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim();
    text = text.replace(/\s+/g, ' ');
    if (text.length > maxLen) text = text.substring(0, maxLen) + '...';
    return text;
  }

  function isInteractive(el) {
    var tag = el.tagName.toLowerCase();
    if (tag === 'button') return true;
    if (tag === 'input' && el.type !== 'hidden') return true;
    if (tag === 'select') return true;
    if (tag === 'textarea') return true;
    if (tag === 'a' && el.href && !el.href.startsWith('javascript:void')) return true;
    if (el.hasAttribute('onclick')) return true;
    var role = (el.getAttribute('role') || '').toLowerCase();
    if (role === 'button' || role === 'link' || role === 'checkbox' || role === 'radio' ||
        role === 'menuitem' || role === 'tab' || role === 'switch' || role === 'option') return true;
    if (el.getAttribute('contenteditable') === 'true') return true;
    return false;
  }

  function sanitizeValue(el) {
    if (el.tagName.toLowerCase() === 'input' && el.type === 'password') return '***';
    return el.value || '';
  }

  function interactiveMode() {
    var candidates = document.querySelectorAll(
      'button, input:not([type="hidden"]), select, textarea, a[href], [onclick], ' +
      '[role="button"], [role="link"], [role="checkbox"], [role="radio"], ' +
      '[role="menuitem"], [role="tab"], [role="switch"], [role="option"], ' +
      '[contenteditable="true"]'
    );
    var elements = [];
    var seen = new Set();
    var visibleCount = 0;
    for (var i = 0; i < candidates.length; i++) {
      var el = candidates[i];
      var rect = isVisible(el);
      if (!rect) continue;
      if (!isInteractive(el)) continue;
      if (seen.has(el)) continue;
      seen.add(el);
      visibleCount++;
      if (elements.length >= MAX_ELEMENTS) continue;
      elements.push({
        ref: '@e' + (elements.length + 1),
        tag: el.tagName.toLowerCase(),
        type: (el.getAttribute('type') || '').toLowerCase(),
        text: getText(el),
        selector: buildSelector(el),
        value: sanitizeValue(el),
        x: rect.left,
        y: rect.top,
        width: rect.width,
        height: rect.height
      });
    }
    var result = { mode: 'interactive', elements: elements };
    if (visibleCount > MAX_ELEMENTS) {
      result.truncated = true;
      result.total_found = visibleCount;
    }
    return result;
  }

  function simplifiedMode() {
    var summary = [];
    var title = document.title;
    if (title) summary.push('Title: ' + title);
    var h1s = document.querySelectorAll('h1');
    if (h1s.length > 0) {
      summary.push('H1: ' + h1s[0].textContent.trim().replace(/\s+/g, ' '));
    }
    var h2s = document.querySelectorAll('h2');
    for (var i = 0; i < Math.min(h2s.length, 5); i++) {
      summary.push('H2: ' + h2s[i].textContent.trim().replace(/\s+/g, ' '));
    }
    var metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) {
      summary.push('Description: ' + (metaDesc.getAttribute('content') || ''));
    }
    var mainText = document.body ? document.body.innerText.replace(/\s+/g, ' ').trim().substring(0, 300) : '';
    if (mainText) summary.push('Body: ' + mainText);

    var lists = [];
    var listEls = document.querySelectorAll('ul, ol');
    for (var j = 0; j < listEls.length; j++) {
      var listEl = listEls[j];
      if (!isVisible(listEl)) continue;
      var items = listEl.querySelectorAll(':scope > li');
      var sampleItems = [];
      for (var k = 0; k < Math.min(items.length, 5); k++) {
        sampleItems.push(items[k].textContent.trim().replace(/\s+/g, ' ').substring(0, 80));
      }
      lists.push({
        selector: buildSelector(listEl),
        tag: listEl.tagName.toLowerCase(),
        item_count: items.length,
        sample_items: sampleItems
      });
    }

    var tables = [];
    var tableEls = document.querySelectorAll('table');
    for (var m = 0; m < tableEls.length; m++) {
      var tableEl = tableEls[m];
      if (!isVisible(tableEl)) continue;
      var headers = [];
      var ths = tableEl.querySelectorAll('th');
      for (var n = 0; n < ths.length; n++) {
        headers.push(ths[n].textContent.trim().replace(/\s+/g, ' '));
      }
      var rows = tableEl.querySelectorAll('tr');
      tables.push({
        selector: buildSelector(tableEl),
        row_count: rows.length,
        col_count: headers.length || (rows.length > 0 ? rows[0].querySelectorAll('td, th').length : 0),
        headers: headers
      });
    }

    return {
      mode: 'simplified',
      summary: summary.join('\n'),
      lists: lists,
      tables: tables
    };
  }

  function simplifyDom(options) {
    options = options || {};
    var mode = options.mode || 'interactive';
    if (mode === 'simplified') return simplifiedMode();
    return interactiveMode();
  }

  return simplifyDom;
})();
