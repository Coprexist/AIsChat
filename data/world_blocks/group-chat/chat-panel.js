/* 群聊对话窗 — 沉浸界面内嵌群聊（chat-panel.js）
 *
 * 样式与主界面聊天保持一致（MessageBubble 同款结构）：
 *   自己 → 右侧紫色渐变头像 + 主色气泡（白字）；别人 → 左侧青色渐变头像 + 表面色气泡
 *   头像：有 sender_avatar_url 用图片，否则渐变 + 首字母；内容走 Markdown 轻量渲染（安全子集）
 *
 * 用法（见 manifest.json usage）：
 *   <div id="group-chat"></div>
 *   <script>
 *     window.GROUP_CHAT_CONFIG = { mountId: 'group-chat', groupId: null, height: '420px', title: '群聊' };
 *   </script>
 *   <script src="blocks/group-chat/chat-panel.js"></script>
 *
 * groupId 默认取 window.GROUP_ID（沉浸入口 /world/{id}/preview 自动注入）。
 * 消息走现有群聊 API（GET/POST /api/groups/{groupId}/messages），沿用登录用户身份。
 */
(function () {
  'use strict';

  var CONFIG = window.GROUP_CHAT_CONFIG || {};
  var MOUNT_ID = CONFIG.mountId || 'group-chat';
  var GROUP_ID = CONFIG.groupId != null ? CONFIG.groupId : (window.GROUP_ID != null ? window.GROUP_ID : null);
  var HEIGHT = CONFIG.height || '420px';
  var TITLE = CONFIG.title || '群聊';
  // API 前缀：优先宿主注入的 WORLD_API（DSH 嵌入 = /aischat-api），其次显式
  // 配置，最后独立部署默认 /api。
  var API_BASE = window.WORLD_API || CONFIG.apiBase || '/api';
  var POLL_MS = CONFIG.pollMs != null ? CONFIG.pollMs : 5000;
  var INITIAL_LIMIT = 50;

  var mount = document.getElementById(MOUNT_ID);
  if (!mount) {
    console.warn('[group-chat] 未找到挂载点 #' + MOUNT_ID);
    return;
  }
  if (GROUP_ID == null) {
    mount.innerHTML = '<div class="gc-hint">群聊对话窗：未配置群聊编号（window.GROUP_ID 为空，可在 GROUP_CHAT_CONFIG.groupId 指定）</div>';
    return;
  }

  var state = { msgs: [], afterId: null, sending: false };
  var timer = null;

  function token() {
    return localStorage.getItem('access_token') || '';
  }

  function headers(json) {
    var h = { 'Authorization': 'Bearer ' + token() };
    if (json) h['Content-Type'] = 'application/json';
    return h;
  }

  // 当前登录用户 id：优先沉浸入口注入的 USER_ID，其次 localStorage（user_info，兼容旧键 user）
  function getMyId() {
    if (window.USER_ID != null) return window.USER_ID;
    try {
      var u = JSON.parse(localStorage.getItem('user_info') || localStorage.getItem('user') || 'null');
      return u && u.id != null ? u.id : null;
    } catch (e) { /* 忽略 */ }
    return null;
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // 后端时间为 naive UTC → 无时区标记时补 'Z'，避免被当本地时间（主界面 parseServerDate 同款）
  function parseDate(s) {
    var hasTz = /[+\-Zz]\d{2}:\d{2}$/.test(s) || /Z$/i.test(s);
    return new Date(hasTz ? s : s + 'Z');
  }

  // 相对时间（主界面 formatMessageTime 同款：刚刚 / X分钟前 / HH:MM / 昨天 HH:MM …）
  function fmtTime(iso) {
    if (!iso) return '';
    var d = parseDate(iso);
    if (isNaN(d.getTime())) return '';
    var now = new Date();
    var diffMin = Math.floor((now - d) / 60000);
    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return diffMin + '分钟前';
    function p(n) { return n < 10 ? '0' + n : '' + n; }
    var hm = p(d.getHours()) + ':' + p(d.getMinutes());
    var dayDiff = Math.floor(
      (new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000
    );
    if (dayDiff <= 0) return hm;
    if (dayDiff === 1) return '昨天 ' + hm;
    if (dayDiff <= 6) return dayDiff + '天前 ' + hm;
    return (d.getMonth() + 1) + '-' + d.getDate() + ' ' + hm;
  }

  function fmtSize(n) {
    if (n == null) return '';
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1048576).toFixed(1) + ' MB';
  }

  // 头像渐变（主界面 avatarGradient 同款：自己紫 / 对方青 / 系统红）
  function avatarGradient(senderType, mine) {
    if (senderType === 'system') return 'linear-gradient(135deg, #fb7185, #e11d48)';
    if (mine) return 'linear-gradient(135deg, #5e81f4, #3f54c4)';
    return 'linear-gradient(135deg, #2dd4bf, #0d9488)';
  }

  // ── Markdown 轻量渲染（主界面 MarkdownContent 的安全子集）──
  // 先整体转义再结构化，杜绝 XSS；支持：标题/粗体/斜体/删除线/行内代码/代码块/链接/引用/列表/分隔线
  function inline(s) {
    s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/~~([^~\n]+)~~/g, '<del>$1</del>');
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    s = s.replace(/\n/g, '<br>');
    return s;
  }

  function md(s) {
    s = esc(s);
    var out = [], inCode = false, codeBuf = [], inList = null, inQuote = false;
    var para = [];
    var lines = s.split('\n');
    function flushList() { if (inList) { out.push(inList === 'ul' ? '</ul>' : '</ol>'); inList = null; } }
    function flushQuote() { if (inQuote) { out.push('</blockquote>'); inQuote = false; } }
    // 连续非空行合成一段（软换行 <br>，主界面 MarkdownContent 同款）
    function flushPara() {
      if (para.length) { out.push('<p>' + para.map(inline).join('<br>') + '</p>'); para = []; }
    }
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (/^```/.test(line)) {
        flushPara(); flushList(); flushQuote();
        if (inCode) {
          out.push('<pre><code>' + codeBuf.join('\n').replace(/\n$/, '') + '</code></pre>');
          codeBuf = []; inCode = false;
        } else {
          inCode = true;
        }
        continue;
      }
      if (inCode) { codeBuf.push(line); continue; }
      var m;
      if ((m = line.match(/^(#{1,4})\s+(.*)$/))) {
        flushPara(); flushList(); flushQuote();
        var lv = m[1].length;
        out.push('<h' + lv + '>' + inline(m[2]) + '</h' + lv + '>');
        continue;
      }
      if (/^\s*---+$/.test(line)) { flushPara(); flushList(); flushQuote(); out.push('<hr>'); continue; }
      if (/^&gt;\s?/.test(line)) {
        flushPara(); flushList();
        if (!inQuote) { out.push('<blockquote>'); inQuote = true; }
        out.push('<p>' + inline(line.replace(/^&gt;\s?/, '')) + '</p>');
        continue;
      }
      if (inQuote) flushQuote();
      var lm;
      if ((lm = line.match(/^\s*[-*+]\s+(.*)$/)) || (lm = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
        flushPara();
        var kind = /^\s*\d+/.test(line) ? 'ol' : 'ul';
        if (!inList) { out.push('<' + kind + '>'); inList = kind; }
        else if (inList !== kind) { flushList(); out.push('<' + kind + '>'); inList = kind; }
        out.push('<li>' + inline(lm[2] != null ? lm[2] : lm[1]) + '</li>');
        continue;
      }
      flushList();
      if (!line.trim()) { flushPara(); continue; }
      para.push(line);
    }
    flushPara(); flushList(); flushQuote();
    if (inCode) out.push('<pre><code>' + codeBuf.join('\n') + '</code></pre>');
    return out.join('\n');
  }

  function render() {
    var list = mount.querySelector('.gc-msgs');
    var prev = list.scrollHeight - list.scrollTop;
    var nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 60;

    if (!state.msgs.length) {
      list.innerHTML = '<div class="gc-empty">还没有消息，说点什么吧</div>';
      return;
    }
    var html = '';
    var myId = getMyId();

    for (var i = 0; i < state.msgs.length; i++) {
      var m = state.msgs[i];
      var mine = myId != null && m.sender_type === 'human' && m.sender_id === myId;
      var isSystem = m.sender_type === 'system';
      var name = m.sender_name || ('#' + m.sender_id);
      var avatarHtml = m.sender_avatar_url
        ? '<img class="gc-avatar" src="' + esc(m.sender_avatar_url) + '" alt="' + esc(name) + '" loading="lazy">'
        : '<div class="gc-avatar" style="background:' + avatarGradient(m.sender_type, mine) + '">' + esc(name.charAt(0).toUpperCase()) + '</div>';
      var body = md(m.content || '');
      var atts = (m.attachments || []).filter(function (a) { return a.type !== 'group_invitation'; });
      if (atts.length) {
        body += '<div class="gc-att">' + atts.map(function (a) {
          if ((a.mime_type || '').indexOf('image/') === 0 && a.file_id != null) {
            return '<img class="gc-att-img" src="' + API_BASE + '/fs/download/' + a.file_id + '?token=' + encodeURIComponent(token()) + '" alt="' + esc(a.name || '图片') + '" loading="lazy">';
          }
          return '<span class="gc-att-chip">📎 ' + esc(a.name || '附件') + (a.size ? ' <i>' + fmtSize(a.size) + '</i>' : '') + '</span>';
        }).join('') + '</div>';
      }
      html += '<div class="gc-msg ' + (mine ? 'gc-mine' : 'gc-theirs') + (isSystem ? ' gc-system' : '') + '">' +
        avatarHtml +
        '<div class="gc-main">' +
        '<div class="gc-head">' +
        '<span class="gc-name">' + esc(name) + '</span>' +
        '<span class="gc-time">' + fmtTime(m.created_at) + '</span>' +
        '</div>' +
        '<div class="gc-bubble">' + body + '</div>' +
        '</div>' +
        '</div>';
    }
    list.innerHTML = html;

    if (nearBottom || prev === 0) {
      list.scrollTop = list.scrollHeight;
    }
  }

  function mergeIncoming(newMsgs) {
    if (!newMsgs || !newMsgs.length) return;
    var known = {};
    state.msgs.forEach(function (m) { known[m.id] = true; });
    var added = false;
    newMsgs.forEach(function (m) {
      if (!known[m.id]) {
        state.msgs.push(m);
        known[m.id] = true;
        added = true;
      }
    });
    state.msgs.sort(function (a, b) { return a.id - b.id; });
    if (state.msgs.length > 500) state.msgs = state.msgs.slice(-500);
    if (added) render();
  }

  function loadInitial() {
    fetch(API_BASE + '/groups/' + GROUP_ID + '/messages?limit=' + INITIAL_LIMIT, { headers: headers(false) })
      .then(function (r) {
        if (r.status === 401) throw new Error('未登录或登录已过期');
        if (!r.ok) throw new Error('拉取消息失败 (' + r.status + ')');
        return r.json();
      })
      .then(function (arr) {
        state.msgs = Array.isArray(arr) ? arr : [];
        state.msgs.sort(function (a, b) { return a.id - b.id; });
        if (state.msgs.length) state.afterId = state.msgs[state.msgs.length - 1].id;
        render();
      })
      .catch(function (e) {
        var list = mount.querySelector('.gc-msgs');
        if (list) list.innerHTML = '<div class="gc-empty">⚠️ ' + esc(e.message) + '</div>';
      });
  }

  function pollNew() {
    if (state.afterId == null) return;
    fetch(API_BASE + '/groups/' + GROUP_ID + '/messages?after_id=' + state.afterId + '&limit=50', { headers: headers(false) })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (arr) {
        if (Array.isArray(arr) && arr.length) {
          state.afterId = arr[arr.length - 1].id;
          mergeIncoming(arr);
        }
      })
      .catch(function () { /* 轮询失败静默，下轮重试 */ });
  }

  function sendMessage() {
    if (state.sending) return;
    var ta = mount.querySelector('.gc-input-row textarea');
    var content = (ta.value || '').trim();
    if (!content) return;
    state.sending = true;
    var btn = mount.querySelector('.gc-send');
    if (btn) btn.disabled = true;

    fetch(API_BASE + '/groups/' + GROUP_ID + '/messages', {
      method: 'POST',
      headers: headers(true),
      body: JSON.stringify({ content: content }),
    })
      .then(function (r) {
        if (r.status === 401) throw new Error('未登录或登录已过期');
        if (!r.ok) return r.json().then(function (d) { throw new Error((d && d.detail) || '发送失败 (' + r.status + ')'); });
        return r.json();
      })
      .then(function (msg) {
        ta.value = '';
        if (msg && msg.id) {
          state.afterId = Math.max(state.afterId || 0, msg.id);
          mergeIncoming([msg]);
        } else {
          loadInitial();
        }
      })
      .catch(function (e) {
        var hint = mount.querySelector('.gc-send-hint');
        if (hint) { hint.textContent = '⚠️ ' + e.message; setTimeout(function () { hint.textContent = ''; }, 3000); }
      })
      .finally(function () {
        state.sending = false;
        if (btn) btn.disabled = false;
        var ta2 = mount.querySelector('.gc-input-row textarea');
        if (ta2) ta2.focus();
      });
  }

  function build() {
    mount.innerHTML =
      '<div class="gc-header">' +
      '<span class="gc-dot"></span>' +
      '<span class="gc-title">' + esc(TITLE) + '</span>' +
      '<button class="gc-refresh" title="刷新">↻</button>' +
      '</div>' +
      '<div class="gc-msgs"></div>' +
      '<div class="gc-input-row">' +
      '<textarea placeholder="发消息给群聊…（Enter 发送，Shift+Enter 换行）"></textarea>' +
      '<button class="gc-send">发送</button>' +
      '</div>' +
      '<div class="gc-hint gc-send-hint"></div>';

    mount.style.height = HEIGHT;

    mount.querySelector('.gc-refresh').addEventListener('click', function () { loadInitial(); });
    mount.querySelector('.gc-send').addEventListener('click', sendMessage);
    mount.querySelector('.gc-input-row textarea').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    loadInitial();
    timer = setInterval(pollNew, POLL_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }

  // 页面卸载清理
  window.addEventListener('pagehide', function () {
    if (timer) clearInterval(timer);
  });
})();
