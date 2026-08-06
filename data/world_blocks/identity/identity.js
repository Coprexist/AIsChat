/* ============================================================
 * 身份系统块 — 把访问界面的用户与世界里的角色对应起来
 *
 * 平台注入变量：window.WORLD_ID / GROUP_ID / USER_ID / USER_NAME / USER_AVATAR
 * 身份命令走群消息（带发送者身份）→ 世界程序 main.py 解析 →
 * 存 world_data（identity.{user_id}）→ publish SSE 状态 → 本页实时显示。
 * 无登录态 / 未绑定群时降级为本地展示（无法登记到世界）。
 * ============================================================ */
(function () {
  'use strict';

  var worldId = window.WORLD_ID;
  var groupId = window.GROUP_ID || null;
  var uid = window.USER_ID || null;
  var uname = window.USER_NAME || '';
  var uavatar = window.USER_AVATAR || '';
  var token = localStorage.getItem('access_token');

  function $(id) { return document.getElementById(id); }

  /* ── 本地身份展示 ── */
  function renderMe() {
    var av = $('my-avatar');
    if (uavatar) av.innerHTML = '<img src="' + uavatar + '" alt="" />';
    else av.textContent = uname ? uname[0] : '?';
    $('my-name').textContent = uname || (uid ? '用户 #' + uid : '未登录');
    $('my-id').textContent = uid ? 'ID: ' + uid : '未登录（请从主应用进入世界）';
  }

  /* ── 发身份命令（群消息 → 世界程序解析，sender_id 即身份） ── */
  function sendCommand(text) {
    if (!groupId) { flash('本世界未绑定群聊，无法登记身份'); return; }
    if (!token) { flash('未登录：请从主界面进入世界'); return; }
    var headers = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token };
    var body = JSON.stringify({ content: text });
    fetch('/api/groups/' + groupId + '/messages', { method: 'POST', headers: headers, body: body })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r; })
      .catch(function () {
        return fetch('/groups/' + groupId + '/messages', { method: 'POST', headers: headers, body: body });
      })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); })
      .then(function () { flash('已发送：' + text); })
      .catch(function (err) { flash('发送失败：' + err.message); });
  }

  var flashTimer = null;
  function flash(msg) {
    var h = $('cmd-hint');
    h.textContent = msg;
    if (flashTimer) clearTimeout(flashTimer);
    flashTimer = setTimeout(function () { h.textContent = ''; }, 4000);
  }

  /* ── SSE：世界程序发布的 identity_state（谁在场/角色） ── */
  function bindWorldEvents() {
    if (!worldId) return;
    var es = new EventSource('/world/' + worldId + '/events');
    es.onmessage = function (e) {
      var state;
      try { state = JSON.parse(e.data); } catch (err) { return; }
      if (state.identity_state) renderUsers(state.identity_state);
      if (state.identity_me && state.identity_me.role) {
        $('my-role').textContent = '世界角色：' + state.identity_me.role;
      }
    };
  }

  function renderUsers(st) {
    var list = st.users || [];
    var box = $('user-list');
    var empty = $('user-empty');
    box.innerHTML = '';
    empty.style.display = list.length ? 'none' : '';
    list.forEach(function (u) {
      var item = document.createElement('div');
      item.className = 'user-item';
      var dot = document.createElement('span');
      dot.className = 'dot';
      item.appendChild(dot);
      var name = document.createElement('span');
      name.textContent = u.name || ('用户 #' + u.id);
      item.appendChild(name);
      if (u.role) {
        var tag = document.createElement('span');
        tag.className = 'tag';
        tag.textContent = u.role;
        item.appendChild(tag);
      }
      var time = document.createElement('span');
      time.className = 'tag';
      time.style.marginLeft = 'auto';
      time.textContent = u.last_seen || '';
      item.appendChild(time);
      box.appendChild(item);
      // 高亮自己
      if (uid && String(u.id) === String(uid)) {
        name.style.color = '#8b9bd6';
        name.style.fontWeight = '600';
      }
    });
  }

  /* ── 事件绑定 ── */
  function init() {
    renderMe();
    $('btn-checkin').addEventListener('click', function () { sendCommand('身份 签到'); });
    $('btn-role').addEventListener('click', function () {
      var role = $('role-input').value.trim();
      if (!role) return;
      sendCommand('身份 我叫 ' + role);
      $('role-input').value = '';
    });
    $('role-input').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') $('btn-role').click();
    });
    bindWorldEvents();
    // 进入页面自动签到一次（世界程序会登记访客）
    if (uid) sendCommand('身份 签到');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
