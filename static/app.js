// Secret Santa Mini App Engine

const tg = window.Telegram?.WebApp;

// Current state
let currentUser = null;


let currentRoom = null;
let botConfig = { bot_username: "SecretSantaBot", webapp_url: window.location.origin };

// Initialize Snow Animation
function initSnow() {
  const canvas = document.getElementById("snow-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let width = (canvas.width = window.innerWidth);
  let height = (canvas.height = window.innerHeight);

  window.addEventListener("resize", () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  });

  const flakes = Array.from({ length: 45 }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    radius: Math.random() * 2.5 + 1,
    speed: Math.random() * 0.8 + 0.3,
    wind: Math.random() * 0.4 - 0.2,
    opacity: Math.random() * 0.6 + 0.2
  }));

  function render() {
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#ffffff";
    for (const f of flakes) {
      ctx.globalAlpha = f.opacity;
      ctx.beginPath();
      ctx.arc(f.x, f.y, f.radius, 0, Math.PI * 2);
      ctx.fill();

      f.y += f.speed;
      f.x += f.wind;
      if (f.y > height) {
        f.y = -5;
        f.x = Math.random() * width;
      }
      if (f.x > width) f.x = 0;
      if (f.x < 0) f.x = width;
    }
    requestAnimationFrame(render);
  }
  render();
}

// Haptic feedback helper
function triggerHaptic(type = "light") {
  if (tg?.HapticFeedback) {
    if (type === "success") tg.HapticFeedback.notificationOccurred("success");
    else if (type === "warning") tg.HapticFeedback.notificationOccurred("warning");
    else if (type === "error") tg.HapticFeedback.notificationOccurred("error");
    else tg.HapticFeedback.impactOccurred("medium");
  }
}

// Toast notification helper
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s";
    setTimeout(() => toast.remove(), 300);
  }, 3200);
}

// Navigation between views
function switchView(viewName) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  const target = document.getElementById(`view-${viewName}`);
  if (target) {
    target.classList.add("active");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Update back button in Telegram WebApp
  if (tg?.BackButton) {
    if (viewName === "home") {
      tg.BackButton.hide();
    } else {
      tg.BackButton.show();
      tg.BackButton.onClick(() => switchView("home"));
    }
  }
}

// API Helper
async function apiCall(endpoint, method = "GET", body = null) {
  try {
    const opts = {
      method,
      headers: { "Content-Type": "application/json" }
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(endpoint, opts);
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Произошла ошибка при обращении к серверу");
    }
    return data;
  } catch (err) {
    showToast(err.message, "error");
    throw err;
  }
}

// Load Bot Config
async function loadConfig() {
  try {
    botConfig = await apiCall("/api/config");
  } catch (e) {
    console.warn("Could not fetch bot config:", e);
  }
}

// Sync current user to DB
async function syncUser() {
  try {
    await apiCall("/api/auth/sync", "POST", currentUser);
    updateUserBadge();
  } catch (e) {
    console.error("Failed to sync user:", e);
  }
}

function updateUserBadge() {
  const nameEl = document.getElementById("user-display-name");
  const subEl = document.getElementById("user-mode-label");
  const avatarEl = document.getElementById("user-avatar");
  if (nameEl) nameEl.textContent = currentUser.first_name;
  if (subEl) subEl.textContent = `@${currentUser.username || currentUser.user_id}`;
  if (avatarEl) {
    const emojis = ["🎅", "🎄", "⛄", "🎁", "🦌", "❄️"];
    const idx = Math.abs(currentUser.user_id) % emojis.length;
    avatarEl.textContent = emojis[idx];
  }
}

// Setup User Detection (Real Telegram WebApp or browser fallback)
function setupUser() {
  if (tg) {
    tg.ready?.();
    tg.expand?.();
  }

  let tu = null;

  // 1. Primary: Telegram WebApp initDataUnsafe.user
  if (tg?.initDataUnsafe?.user?.id) {
    tu = tg.initDataUnsafe.user;
  }

  // 2. Secondary: Parse tg.initData string
  if (!tu && tg?.initData) {
    try {
      const sp = new URLSearchParams(tg.initData);
      const userStr = sp.get("user");
      if (userStr) tu = JSON.parse(userStr);
    } catch (e) {
      console.warn("Could not parse tg.initData:", e);
    }
  }

  // 3. Tertiary: Check window.location.hash for tgWebAppData
  if (!tu && window.location.hash) {
    try {
      const hashParams = new URLSearchParams(window.location.hash.substring(1));
      const tgData = hashParams.get("tgWebAppData");
      if (tgData) {
        const subParams = new URLSearchParams(tgData);
        const userStr = subParams.get("user");
        if (userStr) tu = JSON.parse(userStr);
      }
    } catch (e) {
      console.warn("Could not parse tgWebAppData:", e);
    }
  }

  // If detected real Telegram user
  if (tu && tu.id) {
    currentUser = {
      user_id: tu.id,
      first_name: tu.first_name || "Участник",
      last_name: tu.last_name || "",
      username: tu.username || ""
    };
  } else {
    // Standalone browser fallback: persistent user in localStorage
    let savedId = localStorage.getItem("santa_browser_uid");
    let savedName = localStorage.getItem("santa_browser_name");
    if (!savedId) {
      savedId = String(Math.floor(100000 + Math.random() * 900000));
      savedName = "Пользователь";
      localStorage.setItem("santa_browser_uid", savedId);
      localStorage.setItem("santa_browser_name", savedName);
    }
    currentUser = {
      user_id: parseInt(savedId, 10),
      first_name: savedName,
      last_name: "",
      username: ""
    };
  }

  syncUser();
}


// Load user's rooms
async function loadMyRooms() {
  const listEl = document.getElementById("my-rooms-list");
  if (!listEl) return;

  try {
    const data = await apiCall(`/api/rooms/my?user_id=${currentUser.user_id}`);
    const rooms = data.rooms || [];

    if (rooms.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📭</div>
          <p>У вас пока нет комнат.<br>Создайте новую или присоединитесь по коду друга!</p>
        </div>
      `;
      return;
    }

    listEl.innerHTML = "";
    rooms.forEach((r) => {
      const isLobby = r.status === "LOBBY";
      const statusPill = isLobby
        ? `<span class="status-pill lobby">⏳ В ожидании</span>`
        : `<span class="status-pill started">🎁 Игра началась</span>`;

      const item = document.createElement("div");
      item.className = "room-card-item";
      item.innerHTML = `
        <div class="room-item-info">
          <div class="room-item-title">${escapeHtml(r.title)}</div>
          <div class="room-item-sub">
            <span>👥 ${r.participants_count} уч.</span>
            <span>💰 ${escapeHtml(r.budget || "Любой")}</span>
          </div>
        </div>
        ${statusPill}
      `;
      item.addEventListener("click", () => {
        triggerHaptic();
        loadRoom(r.code);
      });
      listEl.appendChild(item);
    });
  } catch (e) {
    console.error("Error loading rooms:", e);
  }
}

// Create Room Form
function setupCreateRoomForm() {
  const form = document.getElementById("form-create-room");
  const chips = document.querySelectorAll(".chip");
  const budgetInput = document.getElementById("create-budget");

  chips.forEach((c) => {
    c.addEventListener("click", () => {
      chips.forEach((ch) => ch.classList.remove("selected"));
      c.classList.add("selected");
      budgetInput.value = c.dataset.val;
      triggerHaptic();
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = document.getElementById("create-title").value.trim();
    const budget = budgetInput.value.trim();
    const description = document.getElementById("create-desc").value.trim();

    if (!title) {
      showToast("Укажите название комнаты!", "warning");
      return;
    }

    try {
      const res = await apiCall("/api/rooms", "POST", {
        user_id: currentUser.user_id,
        title,
        budget,
        description
      });
      triggerHaptic("success");
      showToast("🎉 Комната успешно создана!", "success");
      form.reset();
      chips.forEach((c) => c.classList.remove("selected"));
      loadRoom(res.room.code);
    } catch (e) {
      // Handled by apiCall
    }
  });
}

// Join by code form
function setupJoinForm() {
  const form = document.getElementById("form-join-code");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const input = document.getElementById("join-code-input");
    const code = input.value.trim().toUpperCase();
    if (!code) return;
    triggerHaptic();
    loadRoom(code);
    input.value = "";
  });
}

// Load and Render Room
async function loadRoom(code) {
  try {
    const data = await apiCall(`/api/rooms/by-code/${code}?user_id=${currentUser.user_id}`);
    currentRoom = data.room;
    renderRoom(data);
    switchView("room");
  } catch (e) {
    // Handled by apiCall
  }
}

function renderRoom(data) {
  const { room, is_admin, is_joined, my_info, participants, stats, target } = data;

  // Auto-join if user opened link and is not joined yet
  if (!is_joined && room.status === "LOBBY") {
    joinCurrentRoom(room.code);
    return;
  }

  // Header and Meta
  document.getElementById("room-title").textContent = room.title;
  document.getElementById("room-desc").textContent = room.description || "";
  document.getElementById("room-budget-val").textContent = room.budget || "Без ограничений";
  document.getElementById("room-participants-count").textContent = stats.total_participants;
  document.getElementById("room-code-val").textContent = room.code;

  const statusTag = document.getElementById("room-header-status");
  const shareBox = document.getElementById("room-share-box");
  const startedSection = document.getElementById("room-started-section");
  const adminSection = document.getElementById("admin-controls-section");

  if (room.status === "LOBBY") {
    statusTag.className = "room-status-tag status-pill lobby";
    statusTag.textContent = "⏳ Ожидание участников";
    shareBox.classList.remove("hidden");
    startedSection.classList.add("hidden");
  } else {
    statusTag.className = "room-status-tag status-pill started";
    statusTag.textContent = "🎉 Игра началась";
    shareBox.classList.add("hidden");
    startedSection.classList.remove("hidden");
  }

  // Render My Wishlist
  renderMyWishlist(my_info);

  // Render Participants
  renderParticipantsList(participants, is_admin, room);

  // Render Readiness progress
  renderReadinessStats(stats);

  // Render Admin Controls
  if (is_admin && room.status === "LOBBY") {
    adminSection.classList.remove("hidden");
    renderAdminPanel(stats, room.code);
  } else {
    adminSection.classList.add("hidden");
  }

  // Render Target Card if game is started
  if (room.status === "STARTED" && target) {
    renderTargetCard(target, room.budget);
  }
}

async function joinCurrentRoom(code) {
  try {
    await apiCall(`/api/rooms/${code}/join`, "POST", {
      user_id: currentUser.user_id,
      wishlist: "",
      anti_wishlist: ""
    });
    showToast("Вы присоединились к комнате!", "success");
    loadRoom(code);
  } catch (e) {
    console.error("Auto-join error:", e);
  }
}

function renderMyWishlist(myInfo) {
  const emptyEl = document.getElementById("my-wish-empty");
  const filledEl = document.getElementById("my-wish-filled");
  const wishTextEl = document.getElementById("my-wish-text");
  const antiWishTextEl = document.getElementById("my-anti-wish-text");

  const hasWish = myInfo && myInfo.wishlist && myInfo.wishlist.trim().length > 0;

  if (hasWish) {
    emptyEl.classList.add("hidden");
    filledEl.classList.remove("hidden");
    wishTextEl.textContent = myInfo.wishlist;
    antiWishTextEl.textContent = myInfo.anti_wishlist || "Не указано (дарите на свой вкус!)";
  } else {
    emptyEl.classList.remove("hidden");
    filledEl.classList.add("hidden");
  }
}

function renderParticipantsList(participants, isAdmin, room) {
  const container = document.getElementById("participants-list");
  container.innerHTML = "";

  participants.forEach((p) => {
    const isMe = p.user_id === currentUser.user_id;
    const item = document.createElement("div");
    item.className = "participant-item";

    const avatarChar = (p.first_name || "У")[0].toUpperCase();
    const readyBadge = p.is_ready
      ? `<span class="badge-ready">✅ Желание готово</span>`
      : `<span class="badge-pending">⏳ Думает</span>`;

    const roleBadge = p.is_creator ? `<span class="participant-role">👑 Организатор</span>` : "";

    let kickBtnHtml = "";
    if (isAdmin && !p.is_creator && room.status === "LOBBY") {
      kickBtnHtml = `<button class="btn-kick" title="Исключить участника" data-kick-id="${p.user_id}">❌</button>`;
    }

    item.innerHTML = `
      <div class="participant-info">
        <div class="participant-avatar">${avatarChar}</div>
        <div class="participant-name-block">
          <div class="participant-name">${escapeHtml(p.first_name)} ${escapeHtml(p.last_name || "")} ${isMe ? "(Вы)" : ""}</div>
          ${roleBadge}
        </div>
      </div>
      <div class="participant-status-block">
        ${readyBadge}
        ${kickBtnHtml}
      </div>
    `;

    // Kick button event
    const kickBtn = item.querySelector(".btn-kick");
    if (kickBtn) {
      kickBtn.addEventListener("click", async () => {
        if (confirm(`Исключить участника ${p.first_name}?`)) {
          triggerHaptic("warning");
          try {
            await apiCall(`/api/rooms/${room.code}/participants/${p.user_id}?user_id=${currentUser.user_id}`, "DELETE");
            showToast("Участник исключён", "info");
            loadRoom(room.code);
          } catch (e) {
            // Handled
          }
        }
      });
    }

    container.appendChild(item);
  });
}

function renderReadinessStats(stats) {
  const statText = document.getElementById("participants-ready-stat");
  const bar = document.getElementById("readiness-bar");
  const hint = document.getElementById("readiness-hint");

  const total = stats.total_participants;
  const ready = stats.ready_count;
  const pct = total > 0 ? Math.round((ready / total) * 100) : 0;

  statText.textContent = `${ready}/${total} готовы`;
  bar.style.width = `${pct}%`;

  if (total < 3) {
    hint.textContent = `⚠️ Нужно минимум 3 участника для запуска игры (сейчас ${total}). Пригласите друзей!`;
    hint.style.color = "var(--warning)";
  } else if (ready < total) {
    hint.textContent = `⏳ Ждём пока все участники напишут свои желания (осталось: ${total - ready}).`;
    hint.style.color = "var(--warning)";
  } else {
    hint.textContent = `✨ Все участники готовы к жеребьёвке! Организатор может запускать.`;
    hint.style.color = "var(--success)";
  }
}

function renderAdminPanel(stats, roomCode) {
  const btnStart = document.getElementById("btn-start-lottery");
  const condText = document.getElementById("start-condition-text");

  if (stats.can_start) {
    btnStart.removeAttribute("disabled");
    condText.textContent = "🎉 Все условия выполнены! Нажмите, чтобы распределить подарки:";
    condText.style.color = "var(--success)";
  } else {
    btnStart.setAttribute("disabled", "true");
    if (stats.total_participants < 3) {
      condText.textContent = `Для запуска нужно минимум 3 участника (сейчас: ${stats.total_participants}).`;
    } else {
      condText.textContent = `Нельзя запустить: ещё ${stats.total_participants - stats.ready_count} участников не написали свои желания.`;
    }
    condText.style.color = "var(--text-muted)";
  }

  // Start Lottery Action
  btnStart.onclick = async () => {
    if (!stats.can_start) return;
    if (!confirm("Запустить жеребьёвку? Каждый участник получит тайного подопечного!")) return;

    triggerHaptic("success");
    try {
      const res = await apiCall(`/api/rooms/${roomCode}/start`, "POST", {
        user_id: currentUser.user_id
      });
      triggerConfetti();
      showToast("🎅 Жеребьёвка успешно завершена!", "success");
      loadRoom(roomCode);
    } catch (e) {
      // Handled
    }
  };
}

function renderTargetCard(target, budget) {
  const boxClosed = document.getElementById("gift-box-closed");
  const boxRevealed = document.getElementById("gift-revealed");
  const targetName = document.getElementById("target-name");
  const targetUser = document.getElementById("target-username");
  const targetProfileLink = document.getElementById("target-profile-link");
  const targetWish = document.getElementById("target-wishlist");
  const targetAnti = document.getElementById("target-anti-wishlist");
  const targetBud = document.getElementById("target-budget-val");

  targetName.textContent = `${target.first_name} ${target.last_name || ""}`.trim();

  // Username and Telegram profile link
  const rawUsername = (target.username || "").trim().replace(/^@/, "");
  let profileUrl = "";

  if (rawUsername) {
    profileUrl = `https://t.me/${rawUsername}`;
    if (targetUser) targetUser.textContent = `@${rawUsername}`;
    if (targetProfileLink) {
      targetProfileLink.href = profileUrl;
      targetProfileLink.classList.remove("disabled-link");
    }
  } else if (target.receiver_id) {
    profileUrl = `tg://user?id=${target.receiver_id}`;
    if (targetUser) targetUser.textContent = `ID: ${target.receiver_id}`;
    if (targetProfileLink) {
      targetProfileLink.href = profileUrl;
      targetProfileLink.classList.remove("disabled-link");
    }
  } else {
    if (targetUser) targetUser.textContent = "Без @username";
    if (targetProfileLink) {
      targetProfileLink.removeAttribute("href");
      targetProfileLink.classList.add("disabled-link");
    }
  }

  // Handle Telegram open link inside Telegram WebApp
  if (profileUrl && targetProfileLink) {
    targetProfileLink.onclick = (e) => {
      triggerHaptic();
      if (tg?.openTelegramLink) {
        e.preventDefault();
        tg.openTelegramLink(profileUrl);
      }
    };
  }

  targetWish.textContent = target.wishlist || "Пожеланий нет (любой сюрприз!)";
  targetAnti.textContent = target.anti_wishlist || "Ограничений нет";
  targetBud.textContent = budget || "Любой";

  // Gift Box Open Click
  boxClosed.onclick = () => {
    triggerHaptic("success");
    triggerConfetti();
    boxClosed.classList.add("hidden");
    boxRevealed.classList.remove("hidden");
  };
}


function triggerConfetti() {
  if (typeof confetti === "function") {
    confetti({
      particleCount: 120,
      spread: 70,
      origin: { y: 0.6 }
    });
  }
}

// Setup Wishlist Modal
function setupWishModal() {
  const modal = document.getElementById("modal-wish");
  const btnEdit = document.getElementById("btn-edit-my-wish");
  const btnFill = document.getElementById("btn-fill-wish-now");
  const btnClose = document.getElementById("btn-close-wish-modal");
  const btnCancel = document.getElementById("btn-cancel-wish");
  const form = document.getElementById("form-wishlist");
  const inputWish = document.getElementById("input-wishlist");
  const inputAnti = document.getElementById("input-anti-wishlist");

  function openModal() {
    triggerHaptic();
    // Fill current values if available
    const curWish = document.getElementById("my-wish-text")?.textContent || "";
    const curAnti = document.getElementById("my-anti-wish-text")?.textContent || "";
    inputWish.value = curWish === "—" ? "" : curWish;
    inputAnti.value = curAnti.startsWith("Не указано") ? "" : curAnti;
    modal.classList.remove("hidden");
  }

  function closeModal() {
    modal.classList.add("hidden");
  }

  btnEdit?.addEventListener("click", openModal);
  btnFill?.addEventListener("click", openModal);
  btnClose?.addEventListener("click", closeModal);
  btnCancel?.addEventListener("click", closeModal);

  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const wishlist = inputWish.value.trim();
    const anti_wishlist = inputAnti.value.trim();

    if (!wishlist) {
      showToast("Пожалуйста, напишите хотя бы одно желание!", "warning");
      return;
    }

    if (!currentRoom) return;

    try {
      await apiCall(`/api/rooms/${currentRoom.code}/wishlist`, "POST", {
        user_id: currentUser.user_id,
        wishlist,
        anti_wishlist
      });
      triggerHaptic("success");
      showToast("Пожелания сохранены! ✅", "success");
      closeModal();
      loadRoom(currentRoom.code);
    } catch (e) {
      // Handled
    }
  });
}

// Setup Share and Invite Buttons
function setupShareActions() {
  const btnCopy = document.getElementById("btn-copy-invite");
  const btnShareTg = document.getElementById("btn-share-tg");

  function getInviteLink() {
    if (!currentRoom) return "";
    if (botConfig.bot_username && botConfig.bot_username !== "SecretSantaBot") {
      return `https://t.me/${botConfig.bot_username}?start=room_${currentRoom.code}`;
    }
    return `${window.location.origin}/?room=${currentRoom.code}`;
  }

  btnCopy?.addEventListener("click", async () => {
    const link = getInviteLink();
    try {
      await navigator.clipboard.writeText(link);
      triggerHaptic("success");
      showToast("Ссылка-приглашение скопирована в буфер!", "success");
    } catch (e) {
      showToast(`Код комнаты: ${currentRoom.code}`, "info");
    }
  });

  btnShareTg?.addEventListener("click", () => {
    const link = getInviteLink();
    const text = encodeURIComponent(`Привет! Заходи ко мне в игру «Тайный Санта» в комнату «${currentRoom.title}»! 🎅🎁\n\n${link}`);
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${text}`;
    
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(shareUrl);
    } else {
      window.open(shareUrl, "_blank");
    }
  });
}

function setupGlobalNavigation() {
  document.getElementById("btn-open-create")?.addEventListener("click", () => {
    triggerHaptic();
    switchView("create");
  });

  document.getElementById("btn-open-join")?.addEventListener("click", () => {
    triggerHaptic();
    switchView("join");
  });

  document.getElementById("btn-refresh-rooms")?.addEventListener("click", () => {
    triggerHaptic();
    loadMyRooms();
    showToast("Список обновлён", "info");
  });

  document.querySelectorAll("[data-back]").forEach((btn) => {
    btn.addEventListener("click", () => {
      triggerHaptic();
      const target = btn.dataset.back;
      if (target === "home") {
        currentRoom = null;
        loadMyRooms();
      }
      switchView(target);
    });
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Check URL Params for deep-links
function checkUrlParams() {
  const urlParams = new URLSearchParams(window.location.search);
  const roomCode = urlParams.get("room") || urlParams.get("startapp");
  const action = urlParams.get("action");

  if (roomCode) {
    const cleanCode = roomCode.replace(/^room_/, "");
    loadRoom(cleanCode);
  } else if (action === "create") {
    switchView("create");
  } else {
    loadMyRooms();
  }
}

// Main Initialization
window.addEventListener("DOMContentLoaded", async () => {
  initSnow();
  await loadConfig();
  setupUser();
  setupGlobalNavigation();
  setupCreateRoomForm();
  setupJoinForm();
  setupWishModal();
  setupShareActions();
  checkUrlParams();
});
