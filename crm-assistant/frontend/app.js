// ---- API helpers ----
let TOKEN = localStorage.getItem("crm_token") || "";
let USER = null;

// Base path so the app works both directly (http://host:8000/) and behind a
// path-prefixed proxy (e.g. https://host/proxy/8000/).
const BASE = window.location.pathname.replace(/\/index\.html?$/i, "").replace(/\/$/, "");
const url = (p) => BASE + p;

async function api(path, opts = {}) {
  opts.headers = opts.headers || {};
  if (TOKEN) opts.headers["Authorization"] = "Bearer " + TOKEN;
  const res = await fetch(url(path), opts);
  if (res.status === 401) { logout(); throw new Error("unauthorized"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "error");
  return data;
}
function jsonPost(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
const $ = (id) => document.getElementById(id);

// Toggle a password field between hidden/visible (eye button).
function togglePass(id, btn){
  const el = document.getElementById(id);
  if (!el) return;
  const show = el.type === "password";
  el.type = show ? "text" : "password";
  if (btn) btn.textContent = show ? "🙈" : "👁️";
}

// ---- มาสคอตผู้ช่วย (ตัวการ์ตูนฟองอากาศน่ารักที่ "ตอบ") ----
const BOT_FACE = `<img src="static/Picture/Logoicon.png" alt="Whisper" />`;

function todayStr(){ return new Date().toLocaleDateString("en-CA"); }  // YYYY-MM-DD (local)
const _MONTHS = ["ม.ค.","ก.พ.","มี.ค.","เม.ย.","พ.ค.","มิ.ย.","ก.ค.","ส.ค.","ก.ย.","ต.ค.","พ.ย.","ธ.ค."];
// Format an ISO date/datetime for display as DD/MMM/YYYY (keeps time if present).
function fmtDate(s){
  if(!s) return "";
  const str = String(s).replace("T"," ");
  const m = str.slice(0,10).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if(!m) return s;
  const out = `${m[3]}/${_MONTHS[parseInt(m[2],10)-1]||m[2]}/${m[1]}`;
  const time = str.slice(11,16);
  return time ? `${out} ${time}` : out;
}
// Show a success message that auto-clears after a few seconds (so it doesn't linger).
function flashOk(el, text, ms = 4000) {
  if (!el) return;
  el.className = "msg";
  el.textContent = text;
  const token = (el._flash = (el._flash || 0) + 1);
  setTimeout(() => { if (el._flash === token) el.textContent = ""; }, ms);
}

// ---- Auth ----
async function login() {
  const body = new URLSearchParams();
  body.set("username", $("login-user").value.trim());
  body.set("password", $("login-pass").value);
  try {
    const res = await fetch(url("/api/auth/login"), { method: "POST", body });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "เข้าสู่ระบบไม่สำเร็จ");
    TOKEN = data.access_token; USER = data.user;
    localStorage.setItem("crm_token", TOKEN);
    showApp();
  } catch (e) { $("login-err").textContent = e.message; }
}
function logout() {
  TOKEN = ""; USER = null; localStorage.removeItem("crm_token");
  $("app-view").classList.add("hidden");
  $("login-view").classList.remove("hidden");
}

const SENS_LABELS = { 1: "1 - ปกติ", 2: "2 - ลับ", 3: "3 - ลับมาก" };
function sensLabel(n){ return SENS_LABELS[n] || ("ระดับ " + n); }

async function showApp() {
  if (!USER) { try { USER = await api("/api/auth/me"); } catch { return logout(); } }
  $("login-view").classList.add("hidden");
  $("app-view").classList.remove("hidden");
  $("who").textContent = `${USER.full_name || USER.username} · ${USER.role} · กลุ่ม: ${USER.department} · เห็นได้ถึง ${sensLabel(USER.allowed_sensitivity)}`;
  document.querySelectorAll(".admin-only").forEach(el => el.classList.toggle("hidden", USER.role !== "admin"));
  const canInputNow = USER.can_input || ["admin","executive","manager"].includes(USER.role);
  if (!canInputNow) {
    document.querySelector('[data-tab="input"]').classList.add("hidden");
    document.querySelectorAll(".input-guard").forEach(el => el.classList.add("hidden"));
  }
  await loadEntities();
  loadIssues();
  loadConvs();
  // default the date fields (Type Data / Add Issue / Log Meeting) to today
  const today = todayStr();
  ["in-date", "is-date", "mt-date"].forEach(id => { const el = $(id); if (el && !el.value) el.value = today; });
  if (CONVS.length) { CUR = CONVS[0]; renderChat(); renderConvList(); }
  else newConv();
}

// ---- Tabs ----
document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  t.classList.add("active");
  const tab = t.dataset.tab;
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.add("hidden"));
  $("tab-" + tab).classList.remove("hidden");
  if (tab === "issues") loadIssues();
  if (tab === "entities") loadEntities();
  if (tab === "manage") searchChunks();
  if (tab === "admin") loadUsers();
}));

// ---- Entities ----
let ENTITIES = [];
const ENTITY_COMBOS = ["chat-entity", "in-entity", "up-entity", "mt-entity", "is-entity", "mg-entity", "iss-filter"];

// Selected entity id for a combo input (null if none/cleared)
function entityId(inputId) {
  const el = $(inputId);
  const v = el && el.dataset ? el.dataset.entityId : "";
  return v ? parseInt(v) : null;
}

function esc2(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

// Combos on the "Add Data" page where a not-found search offers a quick "add name".
const ADDABLE_COMBOS = new Set(["in-entity", "up-entity", "mt-entity", "is-entity"]);

function setupCombo(inputId) {
  const input = $(inputId);
  if (!input || input._comboReady) return;
  input._comboReady = true;
  const allowAdd = ADDABLE_COMBOS.has(inputId);
  const menu = input.nextElementSibling; // .combo-menu
  const render = (filter) => {
    const f = (filter || "").trim().toLowerCase();
    const items = ENTITIES.filter(e =>
      e.name.toLowerCase().includes(f) ||
      (e.industry || "").toLowerCase().includes(f) ||
      (e.registration_no || "").toLowerCase().includes(f) ||
      (e.aliases || []).some(a => (a.alias || "").toLowerCase().includes(f))
    ).slice(0, 60);
    let html = items.map(e => {
      const alias = (e.aliases || []).map(a => a.alias).filter(Boolean).slice(0, 4).join(" · ");
      return `<div class="combo-item" data-id="${e.id}" data-name="${esc2(e.name)}">
         ${esc2(e.name)} <span class="m">· ${e.type}${e.industry ? " · " + esc2(e.industry) : ""}${alias ? " · (" + esc2(alias) + ")" : ""}</span>
       </div>`;
    }).join("");
    if (!items.length) html += '<div class="combo-empty">ไม่พบชื่อที่ตรงกัน</div>';
    // If nothing matches and the user typed a name, offer to add it (input users only).
    const typed = (filter || "").trim();
    if (allowAdd && canInput() && typed && !items.some(e => e.name.toLowerCase() === f)) {
      html += `<div class="combo-add-row">
          <span class="m">เพิ่ม "${esc2(typed)}" เป็น:</span>
          <button type="button" class="combo-add" data-add="customer">➕ ลูกค้า</button>
          <button type="button" class="combo-add" data-add="partner">➕ พาร์ทเนอร์</button>
        </div>`;
    }
    menu.innerHTML = html;
    menu.classList.remove("hidden");
  };
  input.addEventListener("focus", () => { input.select(); render(""); });
  input.addEventListener("input", () => { input.dataset.entityId = ""; render(input.value); });
  input.addEventListener("blur", () => setTimeout(() => menu.classList.add("hidden"), 150));
  menu.addEventListener("mousedown", (e) => {
    const add = e.target.closest(".combo-add");
    if (add) {
      e.preventDefault();
      quickAddEntity(input.value.trim(), add.dataset.add, input, menu);
      return;
    }
    const it = e.target.closest(".combo-item");
    if (!it) return;
    e.preventDefault();
    input.value = it.dataset.name;
    input.dataset.entityId = it.dataset.id;
    menu.classList.add("hidden");
  });
}

// Find existing entities whose name/alias matches (exact) or is similar to a typed name.
function findEntityMatches(name) {
  const n = (name || "").trim().toLowerCase();
  const exact = [], similar = [];
  if (!n) return { exact, similar };
  for (const e of ENTITIES) {
    const labels = [e.name, ...(e.aliases || []).map(a => a.alias)].filter(Boolean);
    let isExact = false, isSim = false;
    for (const L of labels) {
      const l = L.toLowerCase();
      if (l === n) isExact = true;
      else if (l.includes(n) || n.includes(l)) isSim = true;
    }
    if (isExact) exact.push(e);
    else if (isSim) similar.push(e);
  }
  return { exact, similar };
}

// Quickly create an entity from a combo when the name is not found — after confirming
// it is not a duplicate — then select it.
async function quickAddEntity(name, type, input, menu) {
  name = (name || "").trim();
  if (!name) return;
  const typeLabel = type === "partner" ? "พาร์ทเนอร์" : "ลูกค้า";
  const { exact, similar } = findEntityMatches(name);

  let msg;
  if (exact.length) {
    msg = `⚠️ มีชื่อนี้อยู่แล้ว:\n`
        + exact.map(e => `• ${e.name} (${e.type})`).join("\n")
        + `\n\nยังต้องการเพิ่ม "${name}" เป็น${typeLabel} อยู่หรือไม่?`;
  } else if (similar.length) {
    msg = `พบชื่อที่คล้ายกัน (อาจเป็นบริษัทเดียวกัน):\n`
        + similar.slice(0, 6).map(e => `• ${e.name} (${e.type})`).join("\n")
        + `\n\nยืนยันเพิ่ม "${name}" เป็น${typeLabel}ใหม่?`;
  } else {
    msg = `เพิ่ม "${name}" เป็น${typeLabel}ใหม่?`;
  }
  if (!confirm(msg)) return;   // keep the menu open so the user can pick an existing name

  try {
    const r = await jsonPost("/api/entities", { name, type: type || "customer" });
    await loadEntities();               // refresh the shared ENTITIES list
    input.value = name;
    input.dataset.entityId = r.id;      // auto-select the new entity in this combo
    if (menu) menu.classList.add("hidden");
  } catch (e) {
    alert("เพิ่มรายการไม่สำเร็จ: " + e.message);
  }
}

async function loadEntities() {
  ENTITIES = await api("/api/entities");
  ENTITY_COMBOS.forEach(setupCombo);
  const list = $("entities-list");
  if (list) list.innerHTML = ENTITIES.map(e =>
    `<div class="item entity-row" onclick="showEntity(${e.id})">
       <div class="er-main"><div class="t">${esc2(e.name)}</div>
         <div class="m">${e.type} · ${esc2(e.industry||"-")} · แผนก:${e.owner_department}</div></div>
       ${canInput()?`<span class="entity-del" title="ลบรายการนี้" onclick="deleteEntity(${e.id}, event)">🗑️</span>`:""}
     </div>`).join("") || "ไม่มีข้อมูล";
}

async function deleteEntity(id, ev) {
  if (ev) ev.stopPropagation();
  const e = ENTITIES.find(x => x.id === id);
  if (!confirm(`ลบ "${e ? e.name : id}"?\n(ลบได้เฉพาะเมื่อไม่มีบันทึกกิจกรรม — การประชุม / issues / ไฟล์ / ข้อมูลในคลังความรู้)`)) return;
  try {
    await api("/api/entities/" + id, { method: "DELETE" });
    await loadEntities();
    const det = $("entity-detail"); if (det) det.innerHTML = "เลือกจากรายการ";
  } catch (err) { alert("ลบไม่สำเร็จ: " + err.message); }
}
async function createEntity() {
  const m = $("ne-msg"); m.className = "msg";
  const name = $("ne-name").value.trim();
  if (!name) { m.className = "msg error"; m.textContent = "กรุณาระบุชื่อบริษัท/องค์กร"; return; }
  m.textContent = "กำลังบันทึก...";
  try {
    await jsonPost("/api/entities", {
      name,
      type: $("ne-type").value,
      industry: $("ne-industry").value.trim() || null,
      owner_department: $("ne-dept").value.trim() || "general",
      notes: $("ne-notes").value.trim() || null,
      registration_no: $("ne-reg").value.trim() || null,
      short_name: $("ne-short").value.trim() || null,
      name_th: $("ne-th").value.trim() || null,
      name_en: $("ne-en").value.trim() || null,
      ticker: $("ne-ticker").value.trim() || null,
    });
    flashOk(m, "✅ เพิ่มรายการแล้ว");
    ["ne-name","ne-short","ne-th","ne-en","ne-reg","ne-ticker","ne-industry","ne-dept","ne-notes"]
      .forEach(id => { $(id).value = ""; });
    await loadEntities();
  } catch (e) { m.className = "msg error"; m.textContent = "❌ " + e.message; }
}

const ALIAS_LABELS = { short:"ชื่อย่อ", th:"ชื่อภาษาไทย", en:"ชื่อภาษาอังกฤษ", former:"ชื่อเดิม",
                       ticker:"ชื่อย่อหุ้น SET", registration:"เลขทะเบียน", other:"อื่นๆ" };
function canInput(){ return !!(USER && (USER.can_input || ["admin","executive","manager"].includes(USER.role))); }

async function showEntity(id) {
  const d = await api("/api/entities/" + id);
  const e = d.entity;
  const aliases = d.aliases || [];
  const editable = canInput();

  const aliasPills = aliases.map(a =>
    `<span class="alias-pill" title="${esc2(ALIAS_LABELS[a.alias_type]||a.alias_type)}">
       <b>${esc2(ALIAS_LABELS[a.alias_type]||a.alias_type)}:</b> ${esc2(a.alias)}
       ${editable?`<span class="alias-del" title="ลบ" onclick="deleteAlias(${e.id},${a.id})">✕</span>`:""}
     </span>`).join("") || "<span class='m'>ยังไม่มีชื่อ/รหัสเพิ่มเติม</span>";

  const identityBox = `
    <div class="identity">
      <div class="m">🆔 รหัสภายใน (คงที่ — ไม่เปลี่ยนแม้จะเปลี่ยนชื่อ): <b>#${e.id}</b>
        ${e.registration_no?` · เลขทะเบียน: <b>${esc2(e.registration_no)}</b>`:""}</div>
      <div class="alias-wrap">${aliasPills}</div>
      ${editable?`
      <div class="entity-edit">
        <div class="ee-row">
          <input id="rn-name-${e.id}" placeholder="เปลี่ยนชื่อหลักเป็น..." value="${esc2(e.name)}" />
          <button onclick="renameEntity(${e.id})">🔤 เปลี่ยนชื่อ (เก็บชื่อเดิม)</button>
        </div>
        <div class="ee-row">
          <input id="al-text-${e.id}" placeholder="เพิ่มชื่อ / ชื่อย่อ / รหัส" />
          <select id="al-type-${e.id}">
            <option value="short">ชื่อย่อ</option><option value="th">ชื่อภาษาไทย</option>
            <option value="en">ชื่อภาษาอังกฤษ</option><option value="ticker">ชื่อย่อหุ้น SET</option>
            <option value="former">ชื่อเดิม</option><option value="other">อื่นๆ</option>
          </select>
          <button onclick="addAlias(${e.id})">➕ เพิ่ม</button>
        </div>
        <div class="ee-row">
          <select id="et-type-${e.id}">
            <option value="customer" ${e.type==='customer'?'selected':''}>ลูกค้า</option>
            <option value="partner" ${e.type==='partner'?'selected':''}>พาร์ทเนอร์</option>
          </select>
          <input id="et-industry-${e.id}" placeholder="อุตสาหกรรม" value="${esc2(e.industry||'')}" />
          <input id="et-reg-${e.id}" placeholder="เลขนิติบุคคล (ถ้ามี)" value="${esc2(e.registration_no||'')}" />
          <button onclick="saveEntityInfo(${e.id})">💾 บันทึกข้อมูล</button>
        </div>
      </div>`:""}
    </div>`;

  let fin = "";
  try {
    const f = await api("/api/financial/" + id);
    const inRows = (f.internal||[]).map(r => `<li>${r.period}: รายได้ ${r.revenue} ${r.currency}, กำไรสุทธิ ${r.net_profit} (ภายใน)</li>`).join("");
    fin = `<h4>💰 ข้อมูลการเงิน</h4><ul>${inRows||"<li>ไม่มีสิทธิ์เข้าถึงหรือไม่มีข้อมูลภายใน</li>"}</ul>
           <div class="m">🌐 ${f.external?.note||""}</div>`;
  } catch {}
  const historyBox = editable
    ? `<h4>📋 ประวัติ / ข้อมูลบริษัท</h4>
       <textarea id="ent-notes-${e.id}" rows="4" placeholder="บันทึกประวัติ/ภูมิหลัง/ข้อมูลสำคัญของลูกค้า-พาร์ทเนอร์...">${esc2(e.notes||"")}</textarea>
       <button onclick="saveEntityNotes(${e.id})">💾 บันทึกประวัติ</button>
       <div class="msg" id="ent-notes-msg-${e.id}"></div>`
    : (e.notes ? `<h4>📋 ประวัติ / ข้อมูลบริษัท</h4><div>${esc2(e.notes)}</div>` : "");
  $("entity-detail").innerHTML = `
    <div class="t" style="font-size:16px">${esc2(e.name)}</div>
    <div class="m">${e.type} · ${esc2(e.industry||"-")}</div>
    ${identityBox}
    ${historyBox}
    <h4>ผู้ติดต่อ</h4><ul>${d.contacts.map(c=>`<li>${esc2(c.person_name)} — ${esc2(c.title||"")}</li>`).join("")||"<li>-</li>"}</ul>
    <h4>ประวัติการประชุม</h4>${d.interactions.map(i=>`<div class="item"><div class="t">${esc2(fmtDate(i.meeting_date))}</div><div class="m">ฝ่ายเรา: ${esc2(i.our_attendees||"-")} | ฝ่ายเขา: ${esc2(i.their_attendees||"-")}</div><div>${esc2(i.summary||"")}</div></div>`).join("")||"<div class='m'>-</div>"}
    <h4>Issues</h4>${d.issues.map(i=>`<div class="item"><span class="pill ${i.priority}">${i.priority}</span> ${esc2(i.title)} <span class="m">(${i.status})</span></div>`).join("")||"<div class='m'>-</div>"}
    ${fin}`;
}

async function saveEntityInfo(id) {
  const type = $("et-type-" + id) ? $("et-type-" + id).value : undefined;
  const industry = $("et-industry-" + id) ? $("et-industry-" + id).value : undefined;
  const reg = $("et-reg-" + id) ? $("et-reg-" + id).value : undefined;
  if (!confirm("ยืนยันบันทึกข้อมูลบริษัท (ประเภท / อุตสาหกรรม / เลขนิติบุคคล)?")) return;
  try {
    await api("/api/entities/" + id, { method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, industry, registration_no: reg }) });
    await loadEntities();
    showEntity(id);
  } catch (e) { alert("ไม่สำเร็จ: " + e.message); }
}

async function saveEntityNotes(id) {
  const el = $("ent-notes-" + id); if (!el) return;
  const msg = $("ent-notes-msg-" + id);
  if (msg) { msg.className = "msg"; msg.textContent = "กำลังบันทึก..."; }
  try {
    await api("/api/entities/" + id, { method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: el.value }) });
    if (msg) { msg.className = "msg"; msg.textContent = "✅ บันทึกประวัติแล้ว"; }
  } catch (e) {
    if (msg) { msg.className = "msg error"; msg.textContent = "❌ " + e.message; }
  }
}

async function renameEntity(id) {
  const name = $("rn-name-"+id).value.trim();
  if (!name) return;
  if (!confirm(`เปลี่ยนชื่อหลักเป็น "${name}"?\nชื่อเดิมจะถูกเก็บไว้เป็น 'ชื่อเดิม' และยังค้นหาได้ (รหัสภายในไม่เปลี่ยน)`)) return;
  try { await api("/api/entities/"+id, { method:"PUT",
      headers:{ "Content-Type":"application/json" }, body: JSON.stringify({ name }) });
    await loadEntities(); showEntity(id);
  } catch(e){ alert("ไม่สำเร็จ: "+e.message); }
}
async function addAlias(id) {
  const alias = $("al-text-"+id).value.trim();
  if (!alias) return;
  try { await jsonPost("/api/entities/"+id+"/aliases", { alias, alias_type: $("al-type-"+id).value });
    await loadEntities(); showEntity(id);
  } catch(e){ alert("ไม่สำเร็จ: "+e.message); }
}
async function deleteAlias(entityId, aliasId) {
  try { await api(`/api/entities/${entityId}/aliases/${aliasId}`, { method:"DELETE" });
    await loadEntities(); showEntity(entityId);
  } catch(e){ alert("ไม่สำเร็จ: "+e.message); }
}

// ---- Chat with persisted conversations (ChatGPT/Claude style) ----
function esc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

const CONV_KEY = "crm_convs_v1";
let CONVS = [];        // [{id,title,messages:[{role,text,sources}],updated}]
let CUR = null;        // current conversation

function convKey(){ return CONV_KEY + "_" + (USER ? USER.username : "anon"); }
function loadConvs(){ try { CONVS = JSON.parse(localStorage.getItem(convKey())) || []; } catch { CONVS = []; } }
function saveConvs(){ CONVS = CONVS.slice(0, 20); localStorage.setItem(convKey(), JSON.stringify(CONVS)); }

function newConv(){
  CUR = { id: Date.now().toString(36) + Math.random().toString(36).slice(2,6),
          title: "แชทใหม่", messages: [], updated: Date.now() };
  renderChat(); renderConvList();
  $("chat-text").focus();
}
function openConv(id){
  const c = CONVS.find(x => x.id === id);
  if (c) { CUR = c; renderChat(); renderConvList(); }
}
function deleteConv(id, ev){
  if (ev) ev.stopPropagation();
  if (!confirm("ลบแชทนี้?")) return;
  CONVS = CONVS.filter(c => c.id !== id);
  saveConvs();
  if (CUR && CUR.id === id) { CUR = CONVS[0] || null; if (!CUR) newConv(); else renderChat(); }
  renderConvList();
}
function touchConv(){
  CONVS = CONVS.filter(c => c !== CUR);
  CUR.updated = Date.now();
  CONVS.unshift(CUR);
  saveConvs(); renderConvList();
}

function renderConvList(){
  const box = $("conv-list");
  if (!box) return;
  box.innerHTML = CONVS.map(c => `
    <div class="conv-item ${CUR && c.id===CUR.id ? 'active':''}" onclick="openConv('${c.id}')">
      <span class="conv-title">${esc(c.title)}</span>
      <span class="conv-del" title="ลบ" onclick="deleteConv('${c.id}', event)">🗑️</span>
    </div>`).join("") || "<div class='m' style='padding:8px'>ยังไม่มีแชท</div>";
}

function sourcesHtml(sources){
  if (!sources || !sources.length) return "";
  const cards = sources.map(s => {
    if (s.external) {
      if (s.official) {
        return `<div class="src external"><span class="badge official">📊 SET</span>
          <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.source_label||s.url)}</a>
          <div class="m">ข้อมูลทางการจากตลาดหลักทรัพย์แห่งประเทศไทย (SET · ทางการ)</div></div>`;
      }
      return `<div class="src external"><span class="badge external">🌐 ภายนอก</span>
        <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.source_label||s.url)}</a>
        <div class="m">ข้อมูลภายนอก · ยังไม่ยืนยัน</div></div>`;
    }
    return `<div class="src"><span class="badge ${s.label}">${s.label==='fact'?'FACT':s.label==='opinion'?'OPINION':'MIXED'}</span>
     [${s.n}] ${esc(s.source_label||'')}${s.source_person?` — โดย ${esc(s.source_person)}`:''}
     <div class="m">${esc(s.snippet)}...</div>
     ${s.image_url?`<img class="src-img" src="${url(s.image_url)}?token=${encodeURIComponent(TOKEN)}" title="คลิกเพื่อดูขนาดเต็ม" onclick="window.open(this.src,'_blank')" />`:''}
     ${s.id?`<button class="flag-btn" onclick="flagSource(${s.id}, this)">🚩 รายงานว่าไม่ถูกต้อง</button>`:''}</div>`;
  }).join("");
  return `<details class="sources"><summary>ℹ️ แหล่งข้อมูล (${sources.length}) · คลิกเพื่อตรวจสอบ / รายงาน</summary>${cards}</details>`;
}

function bubbleHtml(m){
  if (m.role === "user")
    return `<div class="bubble user"><div class="body">${esc(m.text)}</div></div>`;
  const { text, charts } = extractCharts(m.text);
  const body = `<div class="md">${renderMarkdown(text)}</div>` + chartsHtml(charts)
             + chatImagesHtml(m.sources, m.inline_images) + sourcesHtml(m.sources);
  return `<div class="bubble bot"><div class="avatar">${BOT_FACE}</div><div class="body">${body}</div></div>`;
}

// ---- Chart support: the model may emit a chart as a fenced JSON block ----
// Tolerant: matches ```chart, ```json or a bare ``` fence whose body is JSON that
// looks like a chart spec (has "datasets" or "labels"). Other code blocks stay as text.
function extractCharts(text){
  const charts = [];
  const cleaned = (text || "").replace(/```[a-zA-Z0-9]*\s*([\s\S]*?)```/g, (whole, body) => {
    const t = body.trim();
    if (!(t.startsWith("{") && (t.includes('"datasets"') || t.includes('"labels"')))) return whole;
    try {
      const spec = JSON.parse(t);
      if (spec && (spec.datasets || spec.labels)) { charts.push(spec); return ""; }
    } catch (e) { /* truncated/invalid — leave as text */ }
    return whole;
  });
  return { text: cleaned, charts };
}
function chartsHtml(charts){
  if (!charts || !charts.length) return "";
  return charts.map(spec => {
    const payload = encodeURIComponent(JSON.stringify(spec));
    return `<div class="chat-chart-wrap"><canvas class="chat-chart" data-chart="${payload}"></canvas></div>`;
  }).join("");
}
const CHART_COLORS = ["#f57c00","#1e88e5","#43a047","#e5484d","#8e24aa","#00897b","#fb8c00","#3949ab"];
function initCharts(container){
  if (typeof Chart === "undefined" || !container) return;
  container.querySelectorAll("canvas.chat-chart:not([data-done])").forEach(cv => {
    cv.setAttribute("data-done", "1");
    let spec;
    try { spec = JSON.parse(decodeURIComponent(cv.getAttribute("data-chart"))); }
    catch (e) { return; }
    const type = spec.type || "bar";
    const isPie = (type === "pie" || type === "doughnut");
    const datasets = (spec.datasets || []).map((ds, di) => {
      const base = { label: ds.label || "", data: ds.data || [] };
      if (isPie) {
        base.backgroundColor = (ds.data || []).map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);
      } else {
        const col = CHART_COLORS[di % CHART_COLORS.length];
        base.backgroundColor = (type === "line") ? col + "33" : col;
        base.borderColor = col; base.borderWidth = 2;
        if (type === "line") base.tension = 0.3;
      }
      return base;
    });
    try {
      new Chart(cv.getContext("2d"), {
        type,
        data: { labels: spec.labels || [], datasets },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            title: { display: !!spec.title, text: spec.title || "" },
            legend: { display: isPie || datasets.length > 1 }
          }
        }
      });
    } catch (e) { /* ignore render errors */ }
  });
}

// Show any images from cited sources inline in the answer (not hidden inside the
// collapsed sources panel), so attached pictures are visible directly in chat.
// Skipped for structured queries (financials/contacts) where images are irrelevant.
function chatImagesHtml(sources, allow){
  if (allow === false) return "";
  if (!sources || !sources.length) return "";
  const seen = new Set();
  const imgs = [];
  for (const s of sources){
    if (s.image_url && !seen.has(s.image_url)){ seen.add(s.image_url); imgs.push(s); }
  }
  if (!imgs.length) return "";
  return `<div class="chat-imgs">` + imgs.map(s =>
    `<img class="chat-img" src="${url(s.image_url)}?token=${encodeURIComponent(TOKEN)}"
        title="คลิกเพื่อดูขนาดเต็ม" onclick="window.open(this.src,'_blank')" />`
  ).join("") + `</div>`;
}

// ---- Lightweight Markdown renderer (tables + basic formatting) ----
// Renders assistant answers so GFM pipe-tables show as real HTML tables and
// common markdown (headings, bold/italic, code, lists) reads cleanly.
function mdInline(s){
  // s is already HTML-escaped. Apply inline markdown.
  return s
    .replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
             '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

function isTableSep(line){
  // e.g. | --- | :---: | ---: |
  return /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$/.test(line);
}
function splitRow(line){
  let s = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return s.split("|").map(c => c.trim());
}

function renderMarkdown(text){
  const raw = (text || "").replace(/\r\n/g, "\n");
  const lines = raw.split("\n");
  const out = [];
  let i = 0;
  let para = [];
  let list = null; // {type:'ul'|'ol', items:[]}

  const flushPara = () => {
    if (para.length){ out.push(`<p>${para.map(l => mdInline(esc(l))).join("<br>")}</p>`); para = []; }
  };
  const flushList = () => {
    if (list){ out.push(`<${list.type}>${list.items.map(it => `<li>${mdInline(esc(it))}</li>`).join("")}</${list.type}>`); list = null; }
  };
  const flushAll = () => { flushPara(); flushList(); };

  while (i < lines.length){
    const line = lines[i];

    // Table: header row containing '|' followed by a separator row
    if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])){
      flushAll();
      const header = splitRow(line);
      i += 2; // skip header + separator
      const rows = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== ""){
        rows.push(splitRow(lines[i]));
        i++;
      }
      const thead = `<thead><tr>${header.map(h => `<th>${mdInline(esc(h))}</th>`).join("")}</tr></thead>`;
      const tbody = `<tbody>${rows.map(r =>
        `<tr>${header.map((_, ci) => `<td>${mdInline(esc(r[ci] || ""))}</td>`).join("")}</tr>`).join("")}</tbody>`;
      out.push(`<div class="md-table-wrap"><table class="md-table">${thead}${tbody}</table></div>`);
      continue;
    }

    // Blank line -> paragraph/list break
    if (line.trim() === ""){ flushAll(); i++; continue; }

    // Headings
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h){ flushAll(); const lvl = h[1].length; out.push(`<h${lvl+2} class="md-h">${mdInline(esc(h[2]))}</h${lvl+2}>`); i++; continue; }

    // Ordered list
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (ol){ flushPara(); if (!list || list.type !== "ol"){ flushList(); list = {type:"ol", items:[]}; } list.items.push(ol[1]); i++; continue; }

    // Unordered list
    const ul = line.match(/^\s*[-*+]\s+(.*)$/);
    if (ul){ flushPara(); if (!list || list.type !== "ul"){ flushList(); list = {type:"ul", items:[]}; } list.items.push(ul[1]); i++; continue; }

    // Normal text line
    flushList();
    para.push(line);
    i++;
  }
  flushAll();
  return out.join("");
}

function renderChat(){
  const log = $("chat-log");
  if (!log) return;
  if (!CUR || !CUR.messages.length) {
    log.innerHTML = `<div class="chat-empty">
      <div class="ce-logo">${BOT_FACE}</div>
      <h2>ถามข้อมูลเกี่ยวกับลูกค้า &amp; พาร์ทเนอร์ของคุณ</h2>
      <p class="m">เช่น "เคยเจอบริษัท Whisper เมื่อไหร่, เคยคุยอะไรกันไว้บ้าง"</p>
    </div>`;
    return;
  }
  log.innerHTML = CUR.messages.map(bubbleHtml).join("");
  initCharts(log);
  log.scrollTop = log.scrollHeight;
}

async function sendChat() {
  const q = $("chat-text").value.trim();
  if (!q) return;
  if (!CUR) newConv();
  $("chat-text").value = "";
  autoGrow();

  CUR.messages.push({ role: "user", text: q });
  if (CUR.messages.filter(m => m.role === "user").length === 1) {
    CUR.title = q.length > 40 ? q.slice(0, 40) + "…" : q;
  }
  touchConv();
  renderChat();

  const log = $("chat-log");
  const thinking = document.createElement("div");
  thinking.className = "bubble bot";
  thinking.innerHTML = `<div class="avatar">${BOT_FACE}</div><div class="body">⏳ กำลังค้นหาและวิเคราะห์...</div>`;
  log.appendChild(thinking);
  log.scrollTop = log.scrollHeight;

  try {
    const entity_id = entityId("chat-entity");
    const history = CUR.messages.slice(0, -1).slice(-12).map(m => ({ role: m.role, text: m.text }));
    const res = await jsonPost("/api/chat", { query: q, entity_id, history, model: "haiku" });
    CUR.messages.push({ role: "assistant", text: res.answer, sources: res.sources, inline_images: res.inline_images });
    touchConv();
    renderChat();
  } catch (e) {
    thinking.querySelector(".body").innerHTML = "❌ " + esc(e.message);
  }
}

function autoGrow(){
  const t = $("chat-text");
  t.style.height = "auto";
  t.style.height = Math.min(t.scrollHeight, 160) + "px";
}

// ---- Input actions ----
async function uploadImageFile(file, { entity_id, interaction_id, note, sensitivity, source_label }) {
  const fd = new FormData();
  fd.append("file", file);
  if (entity_id) fd.append("entity_id", entity_id);
  if (interaction_id) fd.append("interaction_id", interaction_id);
  if (note) fd.append("note", note);
  fd.append("sensitivity", sensitivity || 1);
  if (source_label) fd.append("source_label", source_label);
  return api("/api/ingest/image", { method: "POST", body: fd });
}
async function uploadImage(fileInputId, opts) {
  return uploadImageFile($(fileInputId).files[0], opts);
}

async function saveText() {
  const m = $("in-text-msg"); m.className = "msg";
  const text = $("in-text").value;
  const imgs = Array.from($("in-image").files || []);
  if (!text.trim() && !imgs.length) { m.className = "msg error"; m.textContent = "กรุณาพิมพ์ข้อความหรือแนบรูป"; return; }
  const sens = parseInt($("in-sens").value);
  const eid = entityId("in-entity");
  if (!eid) { m.className = "msg error"; m.textContent = "กรุณาเลือกลูกค้า/พาร์ทเนอร์จากรายการก่อนบันทึก"; return; }
  try {
    const parts = [];
    if (text.trim()) {
      m.textContent = "กำลังบันทึกข้อความ...";
      const r = await jsonPost("/api/ingest/text", { text, entity_id: eid, sensitivity: sens, force_label: $("in-flag").value || null, event_date: $("in-date").value || null });
      parts.push(`ข้อความ ${r.stored_chunks} ส่วน`);
    }
    if (imgs.length) {
      let okImg = 0;
      const imgErrors = [];
      for (let i = 0; i < imgs.length; i++) {
        m.textContent = `🖼️ AI กำลังอ่านรูป... (${i + 1}/${imgs.length})`;
        try {
          await uploadImageFile(imgs[i], { entity_id: eid, note: text, sensitivity: sens });
          okImg++;
        } catch (e) { imgErrors.push(`${imgs[i].name}: ${e.message}`); }
      }
      parts.push(`รูป ${okImg}/${imgs.length} ภาพ`);
      if (imgErrors.length) throw new Error("บางรูปอัปโหลดไม่สำเร็จ — " + imgErrors.join(" | "));
    }
    flashOk(m, "✅ บันทึกแล้ว (" + parts.join(", ") + ")");
    $("in-text").value = ""; $("in-image").value = "";
  } catch (e) { m.className = "msg error"; m.textContent = "❌ " + e.message; }
}
async function uploadFile() {
  const m = $("up-msg"); m.className="msg";
  const files = Array.from($("up-file").files || []);
  if (!files.length){ m.className="msg error"; m.textContent="กรุณาเลือกไฟล์ก่อน"; return; }
  const eid = entityId("up-entity");
  if (!eid){ m.className="msg error"; m.textContent="กรุณาเลือกลูกค้า/พาร์ทเนอร์จากรายการก่อนบันทึก"; return; }
  const sens = $("up-sens").value;
  let okCount = 0, totalChunks = 0;
  const errors = [];
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    m.className = "msg";
    m.textContent = `กำลังอัปโหลดและประมวลผล... (${i + 1}/${files.length}) ${f.name}`;
    const fd = new FormData();
    fd.append("file", f);
    fd.append("entity_id", eid);
    fd.append("sensitivity", sens);
    try {
      const r = await api("/api/ingest/file", { method:"POST", body: fd });
      okCount++; totalChunks += (r.stored_chunks || 0);
    } catch(e){ errors.push(`${f.name}: ${e.message}`); }
  }
  if (errors.length) {
    m.className = "msg error";
    m.textContent = `✅ สำเร็จ ${okCount}/${files.length} ไฟล์ · ❌ ${errors.join(" | ")}`;
  } else {
    flashOk(m, `✅ ประมวลผลแล้ว ${okCount} ไฟล์ (รวม ${totalChunks} ส่วน)`);
  }
}
async function saveMeeting() {
  const m = $("mt-msg"); m.className="msg";
  const eid = entityId("mt-entity");
  if (!eid){ m.className="msg error"; m.textContent="กรุณาเลือกลูกค้า/พาร์ทเนอร์จากรายการ"; return; }
  m.textContent="กำลังบันทึก...";
  const sens = parseInt($("mt-sens").value);
  try {
    const res = await jsonPost("/api/interactions", {
      entity_id: eid,
      meeting_date: $("mt-date").value,
      our_attendees: $("mt-ours").value,
      their_attendees: $("mt-theirs").value,
      summary: $("mt-summary").value,
      sensitivity: sens,
    });
    if ($("mt-image").files[0]) {
      m.textContent = "🖼️ AI กำลังอ่านรูป...";
      await uploadImage("mt-image", { entity_id: eid, interaction_id: res.interaction_id,
                                      note: $("mt-summary").value, sensitivity: sens,
                                      source_label: "meeting-image" });
    }
    flashOk(m, "✅ บันทึกการประชุมแล้ว"); $("mt-summary").value=""; $("mt-image").value="";
  } catch(e){ m.className="msg error"; m.textContent="❌ "+e.message; }
}
async function saveIssue() {
  const m = $("is-msg"); m.className="msg";
  const eid = entityId("is-entity");
  if (!eid){ m.className="msg error"; m.textContent="กรุณาเลือกลูกค้า/พาร์ทเนอร์จากรายการ"; return; }
  m.textContent="กำลังบันทึก...";
  try {
    await jsonPost("/api/issues", {
      entity_id: eid,
      title: $("is-title").value,
      description: $("is-desc").value,
      priority: $("is-pri").value,
      sensitivity: parseInt($("is-sens").value),
      event_date: $("is-date").value || null,
    });
    flashOk(m, "✅ บันทึก Issue แล้ว"); $("is-title").value=""; $("is-desc").value="";
    loadIssues();
  } catch(e){ m.className="msg error"; m.textContent="❌ "+e.message; }
}

// ---- Issues ----
let ISSUES_STATUS = "open";
let ISSUES_ROWS = [];
async function loadIssues(status) {
  if (status) ISSUES_STATUS = status;
  const st = ISSUES_STATUS;
  const ob = $("iss-open-btn"), rb = $("iss-resolved-btn");
  if (ob && rb) { ob.classList.toggle("active", st === "open"); rb.classList.toggle("active", st === "resolved"); }
  try {
    ISSUES_ROWS = await api("/api/issues?status=" + st);
    renderIssues();
  } catch(e){ $("issues-list").innerHTML = "<div class='msg error'>"+e.message+"</div>"; }
}
function renderIssues() {
  const st = ISSUES_STATUS;
  // filter by selected/typed customer-partner
  const eid = entityId("iss-filter");
  const q = ($("iss-filter") && $("iss-filter").value || "").trim().toLowerCase();
  let rows = ISSUES_ROWS;
  if (eid) rows = rows.filter(r => r.entity_id === eid);
  else if (q) rows = rows.filter(r => (r.entity_name || "").toLowerCase().includes(q));

  const canResolve = USER && (USER.can_input || ["admin","executive","manager"].includes(USER.role));
  if (st === "resolved") {
    $("issues-list").innerHTML = rows.map(i =>
      `<div class="item"><div class="t">${esc2(i.entity_name)}: ${esc2(i.title)} <span class="pill">✅ แก้แล้ว</span></div>
       ${i.event_date?`<div class="m">📅 ${esc2(fmtDate(i.event_date))}</div>`:""}
       <div class="m">${esc2(i.description||"")}</div>
       <div class="resolved-box"><b>วิธีแก้ไข:</b> ${esc2(i.resolution||"(ไม่ได้ระบุ)")}
         <div class="m">โดย ${esc2(i.resolved_by_name||"-")} · ${esc2(fmtDate(i.resolved_at))}</div>
       </div></div>`
    ).join("") || "<div class='m'>ยังไม่มีประวัติการแก้ไข</div>";
  } else {
    $("issues-list").innerHTML = rows.map(i =>
      `<div class="item"><div class="t">${esc2(i.entity_name)}: ${esc2(i.title)}
        <span class="pill ${i.priority}">${i.priority}</span></div>
       ${i.event_date?`<div class="m">📅 ${esc2(fmtDate(i.event_date))}</div>`:""}
       <div class="m">${esc2(i.description||"")}</div>
       ${canResolve?`<button class="resolve-btn" onclick="toggleResolve(${i.id})">ทำเครื่องหมายว่าแก้แล้ว</button>
       <div class="resolve-form hidden" id="rf-${i.id}">
         <textarea id="rf-text-${i.id}" rows="3" placeholder="อธิบายวิธีที่แก้ไข... (กด Enter เพื่อขึ้นบรรทัดใหม่)"></textarea>
         <div class="rf-actions">
           <button onclick="submitResolve(${i.id})">💾 บันทึกว่าแก้แล้ว</button>
           <button class="btn-soft" onclick="toggleResolve(${i.id})">ยกเลิก</button>
         </div>
       </div>`:""}</div>`
    ).join("") || "<div class='m'>ไม่มี Issue ที่ค้างอยู่ 🎉</div>";
  }
}
function toggleResolve(id) {
  const f = $("rf-" + id);
  if (!f) return;
  f.classList.toggle("hidden");
  if (!f.classList.contains("hidden")) $("rf-text-" + id).focus();
}
async function submitResolve(id) {
  const note = ($("rf-text-" + id).value || "").trim();
  if (!note && !confirm("ยังไม่ได้กรอกรายละเอียดการแก้ไข ต้องการบันทึกว่าแก้แล้วหรือไม่?")) return;
  try {
    await jsonPost(`/api/issues/${id}/resolve`, { resolution: note });
    loadIssues();
  } catch (e) { alert("บันทึกไม่สำเร็จ: " + e.message); }
}

// ---- Flag from chat + Manage/correct data ----
async function flagSource(chunkId, btn) {
  const reason = prompt("ระบุสั้นๆ ว่าข้อมูลนี้ผิดตรงไหน? (ไม่บังคับ):", "");
  if (reason === null) return;
  try {
    await jsonPost(`/api/chunks/${chunkId}/flag`, { reason });
    btn.textContent = "🚩 รายงานแล้ว — ขอบคุณ";
    btn.disabled = true;
  } catch (e) { alert("ไม่สำเร็จ: " + e.message); }
}

async function searchChunks() {
  const box = $("manage-list");
  if (!box) return;
  box.innerHTML = "<div class='m'>กำลังค้นหา...</div>";
  const params = new URLSearchParams();
  const eid = entityId("mg-entity"); if (eid) params.set("entity_id", eid);
  if ($("mg-q").value.trim()) params.set("q", $("mg-q").value.trim());
  if ($("mg-flagged").checked) params.set("flagged", "1");
  try {
    const rows = await api("/api/chunks?" + params.toString());
    if (!rows.length) { box.innerHTML = "<div class='m'>ไม่พบข้อมูล</div>"; return; }
    box.innerHTML = rows.map(c => `
      <div class="mrow ${c.flagged ? 'flagged' : ''}" id="mrow-${c.id}">
        <div class="mrow-head">
          <span class="badge ${c.fact_or_opinion}">${c.fact_or_opinion.toUpperCase()}</span>
          <span class="m">${esc2(c.entity_name||'-')} · ${esc2(c.source_label||'')} · ระดับ ${c.sensitivity}</span>
          <span class="m reporter">👤 ผู้ report: ${esc2(c.reporter_name || c.reporter_username || 'ไม่ระบุ')}</span>
          ${c.flagged ? `<span class="flag-tag">🚩 ${esc2(c.flag_reason||'ถูกรายงาน')}</span>` : ''}
        </div>
        <textarea id="mtext-${c.id}" rows="2">${esc2(c.text)}</textarea>
        <div class="mrow-actions">
          <select id="mlabel-${c.id}">
            <option value="fact" ${c.fact_or_opinion==='fact'?'selected':''}>ข้อเท็จจริง</option>
            <option value="opinion" ${c.fact_or_opinion==='opinion'?'selected':''}>ความเห็น</option>
            <option value="mixed" ${c.fact_or_opinion==='mixed'?'selected':''}>ผสม</option>
          </select>
          <button onclick="saveChunk(${c.id})">💾 บันทึกการแก้ไข</button>
          ${c.flagged ? `<button class="btn-soft" onclick="unflagChunk(${c.id})">ล้างการรายงาน</button>` : ''}
          <button class="btn-danger" onclick="deleteChunk(${c.id})">🗑️ ลบ</button>
        </div>
      </div>`).join("");
  } catch (e) { box.innerHTML = "<div class='msg error'>" + e.message + "</div>"; }
}

async function saveChunk(id) {
  if (!confirm("ยืนยันบันทึกการแก้ไขเนื้อหานี้?\nระบบจะใช้เนื้อหาที่แก้ในการตอบทันที")) return;
  try {
    await api(`/api/chunks/${id}`, { method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("mtext-"+id).value, fact_or_opinion: $("mlabel-"+id).value }) });
    const row = $("mrow-"+id); row.classList.remove("flagged");
    row.querySelector(".mrow-head").insertAdjacentHTML("beforeend", ' <span class="ok">✅ บันทึก + re-embed แล้ว</span>');
  } catch (e) { alert("ไม่สำเร็จ: " + e.message); }
}
async function deleteChunk(id) {
  if (!confirm("ลบถาวรหรือไม่? AI จะไม่ใช้ข้อมูลนี้ในการตอบอีกต่อไป")) return;
  try { await api(`/api/chunks/${id}`, { method: "DELETE" }); $("mrow-"+id).remove(); }
  catch (e) { alert("ไม่สำเร็จ: " + e.message); }
}
async function unflagChunk(id) {
  try { await jsonPost(`/api/chunks/${id}/unflag`, {}); searchChunks(); }
  catch (e) { alert("ไม่สำเร็จ: " + e.message); }
}

// ---- Admin ----
async function loadUsers() {
  try {
    const rows = await api("/api/admin/users");
    $("users-list").innerHTML = rows.map(u =>
      `<div class="item"><div class="t">${u.username} <span class="pill">${u.role}</span></div>
       <div class="m">${u.full_name||""} · กลุ่ม: ${esc2(u.department)} · เห็นได้ถึง ${sensLabel(u.allowed_sensitivity)} · ป้อนข้อมูล: ${u.can_input?"✔":"✖"}</div></div>`
    ).join("");
  } catch(e){ $("users-list").innerHTML="<div class='msg error'>"+e.message+"</div>"; }
}
async function createUser() {
  const m = $("nu-msg"); m.className="msg"; m.textContent="...";
  try {
    await jsonPost("/api/admin/users", {
      username:$("nu-user").value, password:$("nu-pass").value, full_name:$("nu-name").value,
      role:$("nu-role").value, department:$("nu-dept").value||"general",
      allowed_sensitivity:parseInt($("nu-sens").value), can_input:$("nu-input").checked,
    });
    m.textContent="✅ สร้างผู้ใช้แล้ว"; loadUsers();
  } catch(e){ m.className="msg error"; m.textContent="❌ "+e.message; }
}

// ---- Wire up ----
$("login-btn").onclick = login;
$("login-pass").addEventListener("keydown", e => { if (e.key==="Enter") login(); });
$("logout").onclick = logout;
$("chat-send").onclick = sendChat;
$("new-chat").onclick = newConv;
$("chat-text").addEventListener("input", autoGrow);
$("chat-text").addEventListener("keydown", e => { if (e.key==="Enter" && !e.shiftKey){ e.preventDefault(); sendChat(); }});
$("in-text-btn").onclick = saveText;
$("up-btn").onclick = uploadFile;
$("is-btn").onclick = saveIssue;
$("nu-btn").onclick = createUser;
$("ne-btn").onclick = createEntity;
$("iss-open-btn").onclick = () => loadIssues("open");
$("iss-resolved-btn").onclick = () => loadIssues("resolved");
$("iss-filter").addEventListener("input", () => renderIssues());
$("iss-filter").nextElementSibling.addEventListener("mousedown", (e) => {
  if (e.target.closest(".combo-item")) setTimeout(renderIssues, 0);  // re-filter after selecting
});
$("mg-search").onclick = searchChunks;
$("mg-q").addEventListener("keydown", e => { if (e.key==="Enter") searchChunks(); });

// auto-login if token exists
if (TOKEN) showApp();
