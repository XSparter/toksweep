// ==UserScript==
// @name         toksweep request logger
// @namespace    https://github.com/XSparter/toksweep
// @version      1.0
// @description  Logs TikTok web fetch/XHR traffic to the console, one click to copy it as JSON
// @author       XSparter
// @match        https://www.tiktok.com/*
// @grant        none
// @run-at       document-start
// ==/UserScript==

// Kept deliberately small. An earlier version also watched DOM mutations and drew a big
// overlay table, and TikTok simply stopped loading. Console + a copy button is enough.

(function () {
    'use strict';

    const log = [];
    const MAX = 300;

    const asJson = s => {
        if (typeof s !== 'string') return s;
        try { return JSON.parse(s); } catch (_) { return s; }
    };

    const looksLikeDelete = (url, method, body) =>
        method === 'DELETE' ||
        /\/(delete|remove|trash)\b/i.test(url) ||
        (method === 'POST' && /delete/i.test(typeof body === 'string' ? body : ''));

    function record(e) {
        log.unshift(e);
        if (log.length > MAX) log.pop();
        const path = e.url.replace(/^https:\/\/[^/]+/, '');
        const style = looksLikeDelete(e.url, e.method, e.reqBody) ? 'color:#FE2C55;font-weight:bold' : 'color:#25F4EE';
        console.groupCollapsed(`%c[tt] ${e.method} ${e.status} ${path}`, style);
        if (e.reqBody) console.log('request', e.reqBody);
        if (e.resBody) console.log('response', e.resBody);
        console.groupEnd();
    }

    const origFetch = window.fetch.bind(window);
    window.fetch = async function (...args) {
        const req = args[0] instanceof Request ? args[0].clone() : null;
        const url = req ? req.url : String(args[0]);
        const opts = req ? {} : (args[1] || {});
        const method = (req ? req.method : opts.method || 'GET').toUpperCase();
        let reqBody = null;
        try {
            reqBody = req ? asJson(await req.clone().text()) : asJson(opts.body);
        } catch (_) {}

        const res = await origFetch(...args);
        res.clone().text().then(t => record({ url, method, status: res.status, reqBody, resBody: asJson(t) }));
        return res;
    };

    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
        this._tt = { method: String(method).toUpperCase(), url: String(url) };
        return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function (body) {
        if (this._tt) {
            const { method, url } = this._tt;
            const reqBody = typeof body === 'string' ? asJson(body) : (body ? '[binary]' : null);
            this.addEventListener('loadend', () =>
                record({ url, method, status: this.status, reqBody, resBody: asJson(this.responseText) }));
        }
        return origSend.apply(this, arguments);
    };

    function copyLog() {
        const text = JSON.stringify(log, null, 2);
        navigator.clipboard.writeText(text).then(() => {
            btn.textContent = 'copied';
            setTimeout(() => (btn.textContent = 'tt log'), 1500);
        });
    }

    let btn;
    window.addEventListener('load', () => {
        btn = document.createElement('button');
        btn.textContent = 'tt log';
        btn.title = 'Copy captured requests as JSON (Alt+L)';
        Object.assign(btn.style, {
            position: 'fixed', bottom: '16px', right: '16px', zIndex: 2147483647,
            background: '#FE2C55', color: '#fff', border: 0, borderRadius: '16px',
            padding: '6px 14px', font: '600 12px system-ui', cursor: 'pointer',
        });
        btn.onclick = copyLog;
        document.body.appendChild(btn);
    });
    document.addEventListener('keydown', e => { if (e.altKey && e.key === 'l') copyLog(); });
})();
