// Built-in JS utility functions for eval agent
// These are available for reference in browser_eval code — include the function body in your JS.

/**
 * Check if an element matching the CSS selector is visible.
 * @param {string} selector - CSS selector
 * @returns {boolean}
 */
function isVisible(selector) {
    var el = document.querySelector(selector);
    if (!el) return false;
    var style = getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetWidth > 0;
}

/**
 * Retry a function until it returns truthy or max attempts reached.
 * @param {Function} fn - Function to retry (should return truthy on success)
 * @param {number} maxAttempts - Maximum retry attempts (default 10)
 * @param {number} delayMs - Delay between attempts in ms (default 500)
 * @returns {*} The result of fn() or null
 */
function retryUntil(fn, maxAttempts, delayMs) {
    maxAttempts = maxAttempts || 10;
    delayMs = delayMs || 500;
    return new Promise(function(resolve) {
        var attempts = 0;
        function tryOnce() {
            attempts++;
            try {
                var result = fn();
                if (result) { resolve(result); return; }
            } catch(e) {}
            if (attempts >= maxAttempts) { resolve(null); return; }
            setTimeout(tryOnce, delayMs);
        }
        tryOnce();
    });
}

/**
 * Wait for an element to appear in the DOM.
 * @param {string} selector - CSS selector
 * @param {number} timeout - Maximum wait time in ms (default 10000)
 * @returns {Promise<Element|null>}
 */
function waitForElement(selector, timeout) {
    timeout = timeout || 10000;
    return new Promise(function(resolve) {
        var el = document.querySelector(selector);
        if (el) { resolve(el); return; }
        var observer = new MutationObserver(function() {
            var el = document.querySelector(selector);
            if (el) { observer.disconnect(); resolve(el); }
        });
        observer.observe(document.body, { childList: true, subtree: true });
        setTimeout(function() { observer.disconnect(); resolve(null); }, timeout);
    });
}
