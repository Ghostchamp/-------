const state = {
  userId: null,
  money: 0,
  reputation: 0,
  stage: 'employment',
  incomePerSec: 0,
  currentEvent: null,
};

function fakeInitData() {
  return `user=${encodeURIComponent(JSON.stringify({ id: 1001, username: 'demo_master' }))}`;
}

async function api(path, method = 'GET', payload = null) {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

function renderStats() {
  document.getElementById('money').innerText = state.money.toFixed(1);
  document.getElementById('reputation').innerText = state.reputation;
  document.getElementById('stage').innerText = state.stage;
  document.getElementById('income').innerText = state.incomePerSec;
}

function renderEvent(eventData) {
  state.currentEvent = eventData;
  document.getElementById('event-text').innerText = eventData.text;
  const answers = document.getElementById('event-answers');
  answers.innerHTML = '';
  eventData.answers.forEach((answer, idx) => {
    const button = document.createElement('button');
    button.innerText = answer;
    button.onclick = async () => {
      const result = await api('/event/resolve', 'POST', {
        user_id: state.userId,
        event_id: eventData.id,
        answer_index: idx,
      });
      state.money = result.money;
      state.reputation = result.reputation;
      state.incomePerSec = result.income_per_sec;
      renderStats();
      await loadLeaderboard();
      answers.innerHTML = `<em>${result.correct ? 'Верно! ✅' : 'Неудачное решение ❌'}</em>`;
    };
    answers.appendChild(button);
  });
}

async function loadLeaderboard() {
  const board = await api('/leaderboard');
  const root = document.getElementById('leaderboard-list');
  root.innerHTML = '';
  board.items.slice(0, 10).forEach((item) => {
    const li = document.createElement('li');
    li.innerText = `${item.username} — ${item.reputation} (${item.stage})`;
    root.appendChild(li);
  });
}

async function boot() {
  const auth = await api('/auth', 'POST', { init_data: fakeInitData() });
  state.userId = auth.user_id;
  state.money = auth.money;
  state.reputation = auth.reputation;
  state.stage = auth.stage;
  state.incomePerSec = auth.income_per_sec;
  renderStats();
  renderEvent(auth.next_event);
  await loadLeaderboard();

  setInterval(async () => {
    const sync = await api('/sync', 'POST', { user_id: state.userId });
    state.money = sync.money;
    state.reputation = sync.reputation;
    state.stage = sync.stage;
    state.incomePerSec = sync.income_per_sec;
    renderStats();
    renderEvent(sync.next_event);
  }, 15000);

  document.querySelectorAll('#controls button').forEach((btn) => {
    btn.onclick = async () => {
      const skill = btn.dataset.skill;
      try {
        const result = await api('/upgrade', 'POST', {
          user_id: state.userId,
          skill,
        });
        state.money = result.money;
        state.reputation = result.reputation;
        state.stage = result.stage;
        state.incomePerSec = result.income_per_sec;
        renderStats();
        await loadLeaderboard();
      } catch (e) {
        alert('Недостаточно денег для апгрейда');
      }
    };
  });
}

class MiniScene extends Phaser.Scene {
  constructor() {
    super('MiniScene');
  }

  create() {
    this.add.rectangle(420, 180, 840, 360, 0x1d1636).setStrokeStyle(2, 0x7f5ed7);
    this.add.text(24, 18, 'Piercing Studio (MVP)', { fontSize: '20px', color: '#ffffff' });

    this.client = this.add.circle(100, 280, 18, 0xf2c4de);
    this.master = this.add.rectangle(650, 260, 30, 60, 0x90e0ef);

    this.tweens.add({
      targets: this.client,
      x: 580,
      duration: 2800,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.easeInOut',
    });
  }
}

new Phaser.Game({
  type: Phaser.AUTO,
  parent: 'game',
  width: 840,
  height: 360,
  backgroundColor: '#151027',
  scene: [MiniScene],
});

boot();
