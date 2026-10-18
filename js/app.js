/**
 * 库拉马吉风格美股筛选 — 纯静态前端
 * 「一键筛选」：拉取 data/last_scan.json（由 GitHub Actions 用 yfinance 每日刷新），
 * 再在浏览器内按振幅 / 结构勾选做二次过滤。仓位计算纯前端完成。
 */
(function () {
  "use strict";

  const ACCOUNT_USD = 100000;
  const MIN_DOLLAR_VOLUME = ACCOUNT_USD * 100;
  const DATA_URL = "data/last_scan.json";

  let rawData = null;
  let rows = [];
  let sortKey = "RS分";
  let sortAsc = false;

  const $ = (id) => document.getElementById(id);

  function fmtPct(v) {
    if (v == null || v === "") return "—";
    const n = Number(v);
    const cls = n >= 0 ? "pos" : "neg";
    return `<span class="${cls}">${n.toFixed(2)}</span>`;
  }
  function fmtMoney(v) {
    if (v == null) return "—";
    const n = Number(v);
    if (n >= 1e9) return (n / 1e9).toFixed(2) + " 十亿";
    if (n >= 1e6) return (n / 1e6).toFixed(2) + " 百万";
    return n.toLocaleString("zh-CN");
  }
  function flag(v) {
    return v ? `<span class="flag-yes">是</span>` : `<span class="flag-no">否</span>`;
  }

  function renderMarket(m) {
    const box = $("marketBox");
    if (!m || !m.可用) {
      box.innerHTML = `<span><span class="dot gray"></span>${(m && m.说明) || "市场数据不可用"}</span>`;
      return;
    }
    const ok = m.绿色区域;
    box.innerHTML = `
      <span><span class="dot ${ok ? "green" : "red"}"></span>
        ${ok ? "绿色进攻区" : "非绿色区"} · ${m.标的}
      </span>
      <span class="badge ${ok ? "ok" : "warn"}">价 ${m.最新价} / 10日均线 ${m["10日均线"]} / 20日均线 ${m["20日均线"]}</span>
      <span class="meta">${m.说明 || ""}</span>
    `;
  }

  function filterRows(all) {
    let out = all.slice();
    if ($("optAdr").checked) {
      const minAdr = Number($("adrVal").value || 0);
      out = out.filter((r) => (r["20日平均振幅%"] ?? 0) >= minAdr);
    }
    if ($("optStruct").checked) {
      out = out.filter((r) => r.是否贴近均线盘整 || r.接近突破);
    }
    return out;
  }

  function renderTable() {
    const tb = $("tbody");
    $("countBadge").textContent = String(rows.length);
    if (!rows.length) {
      tb.innerHTML = `<tr><td colspan="13" class="empty">无符合条件的标的（可取消振幅过滤再试）</td></tr>`;
      return;
    }
    const sorted = [...rows].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "string") return sortAsc ? av.localeCompare(bv, "zh") : bv.localeCompare(av, "zh");
      return sortAsc ? av - bv : bv - av;
    });
    tb.innerHTML = sorted.map((r) => `
      <tr>
        <td><strong>${r.代码}</strong></td>
        <td title="${r.名称 || ""}">${(r.名称 || r.代码).slice(0, 18)}</td>
        <td>${r.最新价 ?? "—"}</td>
        <td>${fmtPct(r["1月涨幅"])}</td>
        <td>${fmtPct(r["3月涨幅"])}</td>
        <td>${fmtPct(r["6月涨幅"])}</td>
        <td>${fmtMoney(r.日成交额)}</td>
        <td>${r["20日平均振幅%"] ?? "—"}</td>
        <td>${fmtPct(r["距10日均线%"])}</td>
        <td>${fmtPct(r["距20日均线%"])}</td>
        <td>${flag(r.是否贴近均线盘整)}</td>
        <td><strong>${r.建议仓位股数示例 ?? "—"}</strong></td>
        <td>${r.RS分 ?? "—"}</td>
      </tr>
    `).join("");
  }

  function applyResult(data) {
    rawData = data;
    rows = filterRows(data.结果 || []);
    renderMarket(data.市场过滤);
    renderTable();
    const st = data.统计 || {};
    $("statusMeta").textContent =
      `更新：${data.更新时间 || "—"}（${data.时区 || "Asia/Shanghai"}）· 扫描 ${st.扫描数 ?? "—"} · 有效 ${st.有效分析 ?? "—"} · 流动性后 ${st.流动性后 ?? "—"} · 入选 ${st.入选 ?? (data.结果 || []).length} · 当前显示 ${rows.length}`;
  }

  async function loadScanJson(cacheBust) {
    const url = cacheBust ? `${DATA_URL}?t=${Date.now()}` : DATA_URL;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`无法加载筛选数据（HTTP ${res.status}）`);
    return res.json();
  }

  async function doScan() {
    const btn = $("btnScan");
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span>加载筛选数据…`;
    $("statusMeta").textContent = "正在拉取最新预计算结果（data/last_scan.json）…";
    try {
      const data = await loadScanJson(true);
      if (!data.结果) throw new Error(data.说明 || data.错误 || "数据格式无效");
      applyResult(data);
    } catch (e) {
      $("statusMeta").textContent = "错误：" + e.message;
    } finally {
      btn.disabled = false;
      btn.textContent = "一键筛选";
    }
  }

  function refilter() {
    if (!rawData) return;
    rows = filterRows(rawData.结果 || []);
    renderTable();
    const st = rawData.统计 || {};
    $("statusMeta").textContent =
      `更新：${rawData.更新时间 || "—"}（${rawData.时区 || "Asia/Shanghai"}）· 扫描 ${st.扫描数 ?? "—"} · 入选 ${st.入选 ?? (rawData.结果 || []).length} · 当前显示 ${rows.length}`;
  }

  function calcPos() {
    const entry = Number($("entry").value);
    const stop = Number($("stop").value);
    const riskPct = Number($("riskPct").value) / 100;
    const account = ACCOUNT_USD;
    if (!entry || !stop) {
      $("posOut").textContent = "请填写入场价与止损价。";
      return;
    }
    if (entry <= stop || entry <= 0) {
      $("posOut").textContent = "入场价必须高于止损价。";
      return;
    }
    const riskUsd = account * riskPct;
    const shares = Math.floor(riskUsd / (entry - stop));
    const maxOvernight = Math.floor((account * 0.3) / entry);
    const typicalLo = Math.floor((account * 0.1) / entry);
    const typicalHi = Math.floor((account * 0.15) / entry);
    const suggested = Math.min(shares, maxOvernight, typicalHi);
    const notional = suggested * entry;
    $("posOut").innerHTML =
      `风险金额 <strong>${riskUsd.toFixed(2)}</strong> 美元 · 按风险股数 <strong>${shares}</strong> · ` +
      `隔夜上限 <strong>${maxOvernight}</strong> · 典型区间 <strong>${typicalLo}–${typicalHi}</strong><br/>` +
      `建议股数 <strong>${suggested}</strong>（约市值 <strong>${notional.toFixed(2)}</strong> 美元，占账户 <strong>${((notional / account) * 100).toFixed(2)}%</strong>）`;
  }

  $("btnScan").addEventListener("click", doScan);
  $("btnCache").addEventListener("click", doScan);
  $("btnPos").addEventListener("click", calcPos);
  $("optAdr").addEventListener("change", refilter);
  $("optStruct").addEventListener("change", refilter);
  $("adrVal").addEventListener("change", refilter);
  document.querySelectorAll("th[data-k]").forEach((th) => {
    th.addEventListener("click", () => {
      const k = th.getAttribute("data-k");
      if (sortKey === k) sortAsc = !sortAsc;
      else {
        sortKey = k;
        sortAsc = false;
      }
      renderTable();
    });
  });

  // 启动自动加载
  $("statusMeta").textContent =
    `账户 ${ACCOUNT_USD.toLocaleString("zh-CN")} 美元 · 流动性门槛 ${(MIN_DOLLAR_VOLUME / 1e6)} 百万美元 · 正在加载…`;
  loadScanJson(false)
    .then(applyResult)
    .catch((e) => {
      $("statusMeta").textContent =
        `账户 ${ACCOUNT_USD.toLocaleString("zh-CN")} 美元 · 流动性门槛 10 百万美元 · 尚无数据：${e.message}`;
    });
})();
