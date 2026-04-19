#!/usr/bin/env python3
"""
explore.py
==========
A local web UI to explore the road trip SQLite database.
Opens in your browser at http://localhost:5500

Usage:
    pip install flask
    python explore.py --db nl.db
"""

import sqlite3
import json
import math
import argparse
import os
import sys
from pathlib import Path

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Road Trip Explorer</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap');

  :root {
    --bg:      #0f0e0c;
    --surface: #1a1916;
    --border:  #2e2c28;
    --border2: #3d3b36;
    --text:    #e8e4dc;
    --muted:   #7a7670;
    --accent:  #c9a84c;
    --accent2: #8fb87a;
    --mono:    'IBM Plex Mono', monospace;
    --sans:    'IBM Plex Sans', sans-serif;
    --serif:   'Playfair Display', serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: var(--sans); background: var(--bg); color: var(--text); min-height: 100vh; font-size: 14px; line-height: 1.6; }

  .layout { display: flex; height: 100vh; overflow: hidden; }
  .sidebar { width: 240px; flex-shrink: 0; background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
  .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

  .sidebar-head { padding: 18px 14px 12px; border-bottom: 1px solid var(--border); }
  .logo { font-family: var(--serif); font-size: 17px; color: var(--accent); margin-bottom: 2px; }
  .db-name { font-family: var(--mono); font-size: 11px; color: var(--muted); }

  .nav { padding: 8px 6px; border-bottom: 1px solid var(--border); }
  .nav-btn { display: block; width: 100%; text-align: left; padding: 7px 10px; border-radius: 6px; background: none; border: none; color: var(--muted); font-family: var(--sans); font-size: 13px; cursor: pointer; margin-bottom: 2px; transition: all .15s; }
  .nav-btn:hover { background: rgba(255,255,255,.05); color: var(--text); }
  .nav-btn.active { background: rgba(201,168,76,.12); color: var(--accent); }
  .nav-btn .icon { margin-right: 8px; opacity: .7; }

  /* Type filter list in sidebar */
  .type-panel { flex: 1; overflow-y: auto; padding: 10px 6px; }
  .type-panel-head { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); padding: 4px 8px 8px; }
  .type-btn { display: flex; justify-content: space-between; align-items: center; width: 100%; text-align: left; padding: 5px 10px; border-radius: 5px; background: none; border: none; color: var(--muted); font-family: var(--sans); font-size: 12px; cursor: pointer; margin-bottom: 1px; transition: all .12s; }
  .type-btn:hover { background: rgba(255,255,255,.04); color: var(--text); }
  .type-btn.active { background: rgba(201,168,76,.12); color: var(--accent); }
  .type-count { font-family: var(--mono); font-size: 10px; opacity: .6; }

  /* Stats */
  .stats-panel { padding: 10px 14px; border-bottom: 1px solid var(--border); }
  .stat-row { display: flex; justify-content: space-between; padding: 2px 0; }
  .stat-label { font-size: 11px; color: var(--muted); }
  .stat-val { font-family: var(--mono); font-size: 11px; color: var(--accent); }

  /* Toolbar */
  .toolbar { padding: 10px 14px; background: var(--surface); border-bottom: 1px solid var(--border); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .search-wrap { position: relative; flex: 1; min-width: 180px; }
  .search-ico { position: absolute; left: 9px; top: 50%; transform: translateY(-50%); color: var(--muted); font-size: 12px; pointer-events: none; }
  input[type=text], input[type=number], select { background: var(--bg); border: 1px solid var(--border2); border-radius: 7px; color: var(--text); font-family: var(--sans); font-size: 13px; padding: 7px 10px; outline: none; transition: border-color .15s; }
  input[type=text]:focus, input[type=number]:focus, select:focus { border-color: var(--accent); }
  .search-input { width: 100%; padding-left: 28px; }
  select { cursor: pointer; appearance: none; padding-right: 24px; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%237a7670'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 8px center; }
  .btn { padding: 7px 12px; border-radius: 7px; border: 1px solid var(--border2); background: none; color: var(--text); font-family: var(--sans); font-size: 13px; cursor: pointer; transition: all .15s; white-space: nowrap; }
  .btn:hover { border-color: var(--accent); color: var(--accent); }
  .btn-primary { background: rgba(201,168,76,.15); border-color: var(--accent); color: var(--accent); }
  .btn-primary:hover { background: rgba(201,168,76,.25); }

  /* Near form */
  .near-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 8px 14px; background: rgba(201,168,76,.04); border-bottom: 1px solid var(--border); }
  .near-form label { font-size: 12px; color: var(--muted); }
  .near-form input[type=number] { width: 100px; }
  .near-form .radius-input { width: 65px; }
  .near-form.hidden { display: none; }

  .results-meta { padding: 6px 14px; font-size: 12px; color: var(--muted); border-bottom: 1px solid var(--border); background: var(--surface); }
  .results-meta span { color: var(--accent); }

  /* Table */
  .table-wrap { flex: 1; overflow-y: auto; }
  table { width: 100%; border-collapse: collapse; }
  thead th { position: sticky; top: 0; background: var(--surface); padding: 9px 12px; text-align: left; font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); border-bottom: 1px solid var(--border); white-space: nowrap; }
  tbody tr { border-bottom: 1px solid var(--border); cursor: pointer; transition: background .1s; }
  tbody tr:hover { background: rgba(255,255,255,.03); }
  tbody tr.selected { background: rgba(201,168,76,.07); }
  td { padding: 8px 12px; vertical-align: middle; font-size: 13px; }
  .td-id { font-family: var(--mono); font-size: 10px; color: var(--muted); width: 44px; }
  .td-title { font-weight: 500; color: var(--text); max-width: 200px; }
  .td-type { width: 100px; }
  .td-coords { font-family: var(--mono); font-size: 10px; color: var(--muted); white-space: nowrap; }
  .td-spoken { color: var(--muted); font-size: 12px; }
  .td-spoken .preview { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 380px; display: block; }
  .td-dist { font-family: var(--mono); font-size: 11px; color: var(--accent2); white-space: nowrap; }

  /* Type badge */
  .badge { display: inline-block; padding: 2px 7px; border-radius: 10px; font-size: 10px; font-family: var(--mono); font-weight: 500; letter-spacing: .03em; }
  .badge-city       { background: rgba(201,168,76,.18); color: #c9a84c; }
  .badge-town       { background: rgba(201,168,76,.12); color: #c9a84c; }
  .badge-village    { background: rgba(143,184,122,.15); color: #8fb87a; }
  .badge-hamlet     { background: rgba(143,184,122,.10); color: #8fb87a; }
  .badge-municipality { background: rgba(100,150,200,.15); color: #7aaccc; }
  .badge-neighbourhood { background: rgba(100,150,200,.10); color: #7aaccc; }
  .badge-church     { background: rgba(180,140,200,.15); color: #b48cc8; }
  .badge-museum     { background: rgba(180,140,200,.12); color: #b48cc8; }
  .badge-castle     { background: rgba(200,120,100,.15); color: #c87a64; }
  .badge-windmill   { background: rgba(200,120,100,.10); color: #c87a64; }
  .badge-lake       { background: rgba(80,160,200,.15); color: #50a0c8; }
  .badge-canal      { background: rgba(80,160,200,.10); color: #50a0c8; }
  .badge-railway_station { background: rgba(160,160,100,.12); color: #a0a064; }
  .badge-nature_reserve  { background: rgba(143,184,122,.08); color: #6a9858; }
  .badge-other      { background: rgba(122,118,112,.12); color: var(--muted); }
  .badge-skip       { background: rgba(122,118,112,.08); color: #555; }

  /* Pagination */
  .pagination { padding: 8px 14px; background: var(--surface); border-top: 1px solid var(--border); display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); }
  .page-btn { padding: 3px 9px; border-radius: 5px; border: 1px solid var(--border2); background: none; color: var(--text); font-size: 12px; cursor: pointer; }
  .page-btn:hover { border-color: var(--accent); color: var(--accent); }
  .page-btn:disabled { opacity: .3; cursor: default; }
  .page-current { color: var(--accent); font-family: var(--mono); }

  /* Detail panel */
  .detail { width: 360px; flex-shrink: 0; background: var(--surface); border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
  .detail.hidden { display: none; }
  .detail-head { padding: 12px 14px 10px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
  .detail-title-wrap { flex: 1; }
  .detail-title { font-family: var(--serif); font-size: 16px; color: var(--text); line-height: 1.3; margin-bottom: 4px; }
  .close-btn { background: none; border: none; color: var(--muted); font-size: 17px; cursor: pointer; padding: 0 2px; flex-shrink: 0; }
  .close-btn:hover { color: var(--text); }
  .detail-body { padding: 12px 14px; overflow-y: auto; flex: 1; }
  .detail-section { margin-bottom: 16px; }
  .detail-label { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); margin-bottom: 5px; }
  .spoken-text { font-size: 14px; line-height: 1.65; color: var(--text); font-style: italic; }
  .spoken-text::before { content: '"'; color: var(--accent); font-size: 18px; line-height: 0; vertical-align: -4px; margin-right: 2px; }
  .spoken-text::after  { content: '"'; color: var(--accent); font-size: 18px; line-height: 0; vertical-align: -4px; margin-left: 2px; }
  .raw-text { font-size: 11px; color: var(--muted); line-height: 1.6; max-height: 260px; overflow-y: auto; padding: 9px 11px; background: var(--bg); border-radius: 7px; border: 1px solid var(--border); }
  .coord-row { display: flex; gap: 10px; }
  .coord-box { flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: 7px; padding: 7px 9px; }
  .coord-key { font-size: 10px; color: var(--muted); margin-bottom: 2px; }
  .coord-val { font-family: var(--mono); font-size: 12px; color: var(--accent2); }
  .maps-link { display: inline-block; margin-top: 7px; font-size: 12px; color: var(--accent); text-decoration: none; border-bottom: 1px solid rgba(201,168,76,.3); }
  .maps-link:hover { border-color: var(--accent); }

  .empty { padding: 50px 20px; text-align: center; color: var(--muted); }
  .empty-ico { font-size: 32px; margin-bottom: 10px; opacity: .4; }
  .loading { padding: 40px 20px; text-align: center; color: var(--muted); font-size: 13px; }

  ::-webkit-scrollbar { width: 5px; height: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--muted); }
</style>
</head>
<body>
<div class="layout">

  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-head">
      <div class="logo">Road Trip Explorer</div>
      <div class="db-name" id="dbName">loading...</div>
    </div>
    <div class="nav">
      <button class="nav-btn active" onclick="setMode('browse')" id="nav-browse">
        <span class="icon">&#9776;</span> Browse all
      </button>
      <button class="nav-btn" onclick="setMode('near')" id="nav-near">
        <span class="icon">&#9906;</span> Find nearby
      </button>
    </div>
    <div class="stats-panel" id="statsPanel">
      <div class="stat-row"><span class="stat-label">Loading…</span></div>
    </div>
    <div class="type-panel">
      <div class="type-panel-head">Filter by type</div>
      <button class="type-btn active" onclick="setType('')" id="type-all">
        <span>All</span><span class="type-count" id="type-count-all">—</span>
      </button>
      <div id="typeList"></div>
    </div>
  </div>

  <!-- Main -->
  <div class="main">
    <div class="toolbar">
      <div class="search-wrap">
        <span class="search-ico">&#128269;</span>
        <input type="text" class="search-input" id="searchInput"
               placeholder="Search titles and spoken text…"
               oninput="onSearch()">
      </div>
      <button class="btn" onclick="clearSearch()">Clear</button>
      <select id="langSelect" onchange="onLangChange()" title="Language">
        <option value="en">🇬🇧 EN</option>
        <option value="nl">🇳🇱 NL</option>
      </select>
    </div>

    <div class="near-form hidden" id="nearForm">
      <label>Lat</label>
      <input type="number" id="nearLat" value="52.37" step="0.001" style="width:105px">
      <label>Lon</label>
      <input type="number" id="nearLon" value="4.89" step="0.001" style="width:105px">
      <label>Radius (km)</label>
      <input type="number" id="nearRadius" value="5" min="0.5" max="100" step="0.5" class="radius-input">
      <button class="btn btn-primary" onclick="doNearSearch()">Search</button>
    </div>

    <div class="results-meta" id="resultsMeta">Loading…</div>

    <div style="display:flex;flex:1;overflow:hidden">
      <div class="table-wrap" id="tableWrap">
        <div class="loading">Loading database…</div>
      </div>

      <!-- Detail panel -->
      <div class="detail hidden" id="detail">
        <div class="detail-head">
          <div class="detail-title-wrap">
            <div class="detail-title" id="detailTitle">—</div>
            <span id="detailBadge"></span>
          </div>
          <button class="close-btn" onclick="closeDetail()">&#x2715;</button>
        </div>
        <div class="detail-body">
          <div class="detail-section">
            <div class="detail-label">Spoken text</div>
            <div class="spoken-text" id="detailSpoken">—</div>
          </div>
          <div class="detail-section">
            <div class="detail-label">Coordinates</div>
            <div class="coord-row">
              <div class="coord-box"><div class="coord-key">Latitude</div><div class="coord-val" id="detailLat">—</div></div>
              <div class="coord-box"><div class="coord-key">Longitude</div><div class="coord-val" id="detailLon">—</div></div>
            </div>
            <a class="maps-link" id="detailMaps" href="#" target="_blank">Open in Google Maps ↗</a>
          </div>
          <div class="detail-section">
            <div class="detail-label">Wikipedia source text</div>
            <div class="raw-text" id="detailRaw">—</div>
          </div>
        </div>
      </div>
    </div>

    <div class="pagination" id="pagination" style="display:none">
      <button class="page-btn" id="prevBtn" onclick="prevPage()">← Prev</button>
      <span>Page <span class="page-current" id="pageNum">1</span> of <span id="pageTotal">1</span></span>
      <button class="page-btn" id="nextBtn" onclick="nextPage()">Next →</button>
      <span style="margin-left:auto">Showing <span id="pageRange">—</span></span>
    </div>
  </div>

</div>

<script>
var PAGE_SIZE = 50;
var currentPage = 1;
var currentRows = [];
var mode = 'browse';
var activeType = '';
var activeLang = 'en';
var searchTimer = null;

function onLangChange() {
  activeLang = document.getElementById('langSelect').value;
  loadPage(1, document.getElementById('searchInput').value.trim(), activeType);
}

window.onload = function() {
  loadStats();
  loadPage(1, '', '');
};

function setMode(m) {
  mode = m;
  document.getElementById('nav-browse').classList.toggle('active', m === 'browse');
  document.getElementById('nav-near').classList.toggle('active', m === 'near');
  document.getElementById('nearForm').classList.toggle('hidden', m !== 'near');
  document.getElementById('searchInput').value = '';
  closeDetail();
  if (m === 'browse') loadPage(1, '', activeType);
  else { renderTable([], 0); document.getElementById('resultsMeta').textContent = 'Enter coordinates and click Search'; }
}

function typeId(t) { return 'type-' + t.replace(/\s+/g, '_'); }

function setType(t) {
  activeType = t;
  document.querySelectorAll('.type-btn').forEach(function(b) { b.classList.remove('active'); });
  var sel = t ? document.getElementById(typeId(t)) : document.getElementById('type-all');
  if (sel) sel.classList.add('active');
  loadPage(1, document.getElementById('searchInput').value.trim(), t);
}

function onSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(function() {
    loadPage(1, document.getElementById('searchInput').value.trim(), activeType);
  }, 250);
}

function clearSearch() {
  document.getElementById('searchInput').value = '';
  loadPage(1, '', activeType);
}

function loadStats() {
  fetch('/api/stats').then(function(r){return r.json();}).then(function(d) {
    document.getElementById('dbName').textContent = d.db;
    document.getElementById('type-count-all').textContent = d.total.toLocaleString();
    var html = '';
    html += '<div class="stat-row"><span class="stat-label">Total</span><span class="stat-val">' + d.total.toLocaleString() + '</span></div>';
    html += '<div class="stat-row"><span class="stat-label">Avg spoken</span><span class="stat-val">' + d.avg_len + ' ch</span></div>';
    html += '<div class="stat-row"><span class="stat-label">With type</span><span class="stat-val">' + d.has_type.toLocaleString() + '</span></div>';
    document.getElementById('statsPanel').innerHTML = html;

    // Build type filter list
    var typeHtml = '';
    d.types.forEach(function(t) {
      if (t.type === 'skip') return;
      var sid = typeId(t.type);
      typeHtml += '<button class="type-btn" data-type="' + escHtml(t.type) + '" id="' + sid + '">';
      typeHtml += '<span>' + badge(t.type) + ' ' + escHtml(t.type) + '</span>';
      typeHtml += '<span class="type-count">' + t.count.toLocaleString() + '</span>';
      typeHtml += '</button>';
    });
    document.getElementById('typeList').innerHTML = typeHtml;
    // Attach click handlers after inserting HTML
    document.querySelectorAll('#typeList .type-btn').forEach(function(btn) {
      btn.addEventListener('click', function() { setType(this.getAttribute('data-type')); });
    });
  });
}

function loadPage(page, q, type) {
  currentPage = page;
  var url = '/api/locations?page=' + page + '&q=' + encodeURIComponent(q) + '&type=' + encodeURIComponent(type || '') + '&lang=' + activeLang;
  document.getElementById('tableWrap').innerHTML = '<div class="loading">Fetching ' + url + '…</div>';
  fetch(url).then(function(r){
    document.getElementById('tableWrap').innerHTML = '<div class="loading">HTTP ' + r.status + ', parsing JSON…</div>';
    return r.json();
  }).then(function(d) {
    document.getElementById('tableWrap').innerHTML = '<div class="loading">Got ' + (d.rows ? d.rows.length : '?') + ' rows, total=' + d.total + ', rendering…</div>';
    currentRows = d.rows;
    renderTable(d.rows, d.total);
    renderPagination(page, d.total);
    var meta = '<span>' + d.total.toLocaleString() + '</span> locations';
    if (type) meta += ' of type <em>' + escHtml(type) + '</em>';
    if (q)    meta += ' matching <em>"' + escHtml(q) + '"</em>';
    document.getElementById('resultsMeta').innerHTML = meta;
  }).catch(function(e) {
    document.getElementById('tableWrap').innerHTML = '<div class="empty"><div class="empty-msg">Error: ' + e + '</div></div>';
  });
}

function doNearSearch() {
  var lat    = parseFloat(document.getElementById('nearLat').value);
  var lon    = parseFloat(document.getElementById('nearLon').value);
  var radius = parseFloat(document.getElementById('nearRadius').value);
  if (isNaN(lat) || isNaN(lon)) { alert('Enter valid coordinates'); return; }
  var url = '/api/nearby?lat=' + lat + '&lon=' + lon + '&radius=' + radius +
            '&type=' + encodeURIComponent(activeType || '') + '&lang=' + activeLang;
  fetch(url).then(function(r){return r.json();}).then(function(d) {
    currentRows = d.rows;
    renderTable(d.rows, d.rows.length, true);
    document.getElementById('pagination').style.display = 'none';
    document.getElementById('resultsMeta').innerHTML =
      '<span>' + d.rows.length + '</span> locations within ' + radius + ' km of (' + lat + ', ' + lon + ')';
  });
}

function badge(type) {
  var cls = 'badge badge-' + (type || 'other').replace(/\s+/g, '_');
  return '<span class="' + cls + '">' + escHtml(type || 'other') + '</span>';
}

function renderTable(rows, total, showDist) {
  var wrap = document.getElementById('tableWrap');
  if (!rows.length) {
    wrap.innerHTML = '<div class="empty"><div class="empty-ico">&#128269;</div><div class="empty-msg">No results found</div></div>';
    return;
  }
  var html = '<table><thead><tr><th>#</th><th>Title</th><th>Type</th><th>Coordinates</th>';
  if (showDist) html += '<th>Dist</th>';
  html += '<th>Spoken text</th></tr></thead><tbody>';
  rows.forEach(function(row) {
    html += '<tr onclick="showDetail(' + row.id + ', this)">';
    html += '<td class="td-id">' + row.id + '</td>';
    html += '<td class="td-title">' + escHtml(row.title) + '</td>';
    html += '<td class="td-type">' + badge(row.type) + '</td>';
    html += '<td class="td-coords">' + row.lat.toFixed(4) + ', ' + row.lon.toFixed(4) + '</td>';
    if (showDist) html += '<td class="td-dist">' + (row.dist_km || 0).toFixed(1) + ' km</td>';
    html += '<td class="td-spoken"><span class="preview">' + escHtml(row.spoken_text) + '</span></td>';
    html += '</tr>';
  });
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

function renderPagination(page, total) {
  var pages = Math.ceil(total / PAGE_SIZE);
  var pg = document.getElementById('pagination');
  if (pages <= 1) { pg.style.display = 'none'; return; }
  pg.style.display = 'flex';
  document.getElementById('pageNum').textContent = page;
  document.getElementById('pageTotal').textContent = pages;
  document.getElementById('prevBtn').disabled = page <= 1;
  document.getElementById('nextBtn').disabled = page >= pages;
  var from = (page-1)*PAGE_SIZE+1, to = Math.min(page*PAGE_SIZE, total);
  document.getElementById('pageRange').textContent = from + '–' + to + ' of ' + total.toLocaleString();
}

function prevPage() {
  if (currentPage > 1) loadPage(currentPage-1, document.getElementById('searchInput').value.trim(), activeType);
}
function nextPage() {
  loadPage(currentPage+1, document.getElementById('searchInput').value.trim(), activeType);
}

function showDetail(id, el) {
  var row = null;
  for (var i=0; i<currentRows.length; i++) { if (currentRows[i].id===id) { row=currentRows[i]; break; } }
  if (!row) return;
  document.querySelectorAll('tbody tr').forEach(function(tr) { tr.classList.remove('selected'); });
  if (el) el.classList.add('selected');
  document.getElementById('detail').classList.remove('hidden');
  document.getElementById('detailTitle').textContent = row.title;
  document.getElementById('detailBadge').innerHTML = badge(row.type);
  document.getElementById('detailSpoken').textContent = row.spoken_text;
  document.getElementById('detailLat').textContent = row.lat.toFixed(6);
  document.getElementById('detailLon').textContent = row.lon.toFixed(6);
  document.getElementById('detailMaps').href = 'https://www.google.com/maps?q=' + row.lat + ',' + row.lon;
  document.getElementById('detailRaw').textContent = 'Loading…';
  fetch('/api/raw/' + id).then(function(r){return r.json();}).then(function(d) {
    document.getElementById('detailRaw').textContent = d.raw || '(no source text)';
  });
}

function closeDetail() {
  document.getElementById('detail').classList.add('hidden');
  document.querySelectorAll('tbody tr').forEach(function(tr) { tr.classList.remove('selected'); });
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------
def create_app(db_path):
    try:
        from flask import Flask, jsonify, request, Response
    except ImportError:
        print("Error: Flask not installed. Run: pip install flask")
        sys.exit(1)

    app = Flask(__name__)
    PAGE_SIZE = 50

    def get_db():
        return sqlite3.connect(db_path)

    def get_lang(req):
        return req.args.get("lang", "en")

    @app.route("/")
    def index():
        return Response(HTML, mimetype="text/html")

    @app.route("/api/stats")
    def stats():
        conn = get_db()
        c    = conn.cursor()
        total    = c.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        avg_len  = c.execute(
            "SELECT ROUND(AVG(LENGTH(spoken_text))) FROM location_texts WHERE language='en'"
        ).fetchone()[0]
        has_type = c.execute("SELECT COUNT(*) FROM locations WHERE type IS NOT NULL").fetchone()[0]

        # Languages available
        langs = [r[0] for r in c.execute(
            "SELECT DISTINCT language FROM location_texts ORDER BY language"
        ).fetchall()]

        # Type breakdown
        type_rows = c.execute(
            "SELECT COALESCE(type,'other') as t, COUNT(*) as n "
            "FROM locations GROUP BY t ORDER BY n DESC"
        ).fetchall()
        conn.close()

        return jsonify(
            db=os.path.basename(db_path),
            total=total,
            avg_len=int(avg_len or 0),
            has_type=has_type,
            languages=langs,
            types=[{"type": r[0], "count": r[1]} for r in type_rows]
        )

    @app.route("/api/locations")
    def locations():
        page   = int(request.args.get("page", 1))
        q      = request.args.get("q", "").strip()
        type_  = request.args.get("type", "").strip()
        lang   = get_lang(request)
        offset = (page - 1) * PAGE_SIZE
        conn   = get_db()
        c      = conn.cursor()

        conditions = ["lt.language = ?"]
        params     = [lang]
        if q:
            conditions.append("(l.title LIKE ? OR lt.spoken_text LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        if type_:
            conditions.append("l.type = ?")
            params.append(type_)

        where = "WHERE " + " AND ".join(conditions)
        base  = "FROM locations l JOIN location_texts lt ON lt.location_id = l.id"

        total = c.execute(f"SELECT COUNT(*) {base} {where}", params).fetchone()[0]
        rows  = c.execute(
            f"SELECT l.id, l.title, l.lat, l.lon, lt.spoken_text, l.type "
            f"{base} {where} ORDER BY l.title LIMIT ? OFFSET ?",
            params + [PAGE_SIZE, offset]
        ).fetchall()
        conn.close()

        return jsonify(total=total, rows=[
            {"id": r[0], "title": r[1], "lat": r[2], "lon": r[3],
             "spoken_text": r[4], "type": r[5]}
            for r in rows
        ])

    @app.route("/api/nearby")
    def nearby():
        lat    = float(request.args.get("lat", 52.37))
        lon    = float(request.args.get("lon", 4.89))
        radius = float(request.args.get("radius", 5.0))
        type_  = request.args.get("type", "").strip()
        lang   = get_lang(request)
        dlat   = radius / 111.0
        dlon   = radius / (111.0 * abs(math.cos(math.radians(lat))))

        conn   = get_db()
        c      = conn.cursor()

        conditions = [
            "lt.language = ?",
            "l.lat BETWEEN ? AND ?",
            "l.lon BETWEEN ? AND ?",
        ]
        params = [lang, lat-dlat, lat+dlat, lon-dlon, lon+dlon]
        if type_:
            conditions.append("l.type = ?")
            params.append(type_)

        where = "WHERE " + " AND ".join(conditions)
        rows  = c.execute(
            f"SELECT l.id, l.title, l.lat, l.lon, lt.spoken_text, l.type "
            f"FROM locations l JOIN location_texts lt ON lt.location_id = l.id "
            f"{where}",
            params
        ).fetchall()
        conn.close()

        result = []
        for r in rows:
            dist = math.sqrt((r[2]-lat)**2 + (r[3]-lon)**2) * 111
            if dist <= radius:
                result.append({"id": r[0], "title": r[1], "lat": r[2], "lon": r[3],
                                "spoken_text": r[4], "type": r[5], "dist_km": round(dist, 2)})
        result.sort(key=lambda x: x["dist_km"])
        return jsonify(rows=result)

    @app.route("/api/raw/<int:loc_id>")
    def raw(loc_id):
        conn = get_db()
        row  = conn.execute(
            "SELECT raw_summary FROM locations WHERE id = ?", (loc_id,)
        ).fetchone()
        conn.close()
        return jsonify(raw=row[0] if row else "")

    return app


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Explore road trip SQLite database in browser")
    parser.add_argument("--db",   default="nl.db", help="SQLite database file (default: nl.db)")
    parser.add_argument("--port", type=int, default=5500, help="Port (default: 5500)")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Error: {args.db} not found.")
        sys.exit(1)

    app = create_app(args.db)

    print(f"\n  Road Trip Explorer")
    print(f"  Database : {args.db}")
    print(f"  URL      : http://localhost:{args.port}")
    print(f"\n  Press Ctrl+C to stop\n")

    import webbrowser, threading
    threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()
    app.run(port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
