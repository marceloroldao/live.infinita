(() => {
  const statusEl = document.getElementById('status');
  const narrationEl = document.getElementById('narration');
  const versionEl = document.getElementById('version');
  const simulatorEl = document.getElementById('simulator');

  const app = new PIXI.Application();
  let worldContainer = null;
  let ground = null;

  async function boot() {
    await app.init({ resizeTo: window, background: '#18251a', antialias: true });
    document.getElementById('scene').appendChild(app.canvas);
    drawGround('day');
    bindSimulator();
    connect();
  }

  function drawGround(period = 'day') {
    if (ground) app.stage.removeChild(ground);
    ground = new PIXI.Graphics();
    const night = period === 'night';
    ground.rect(0, 0, 4096, 4096).fill(night ? 0x07101c : 0x18251a);
    ground.circle(460, 300, 260).fill(night ? 0x17263a : 0x304b2f);
    app.stage.addChildAt(ground, 0);
  }

  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
      statusEl.textContent = 'conectado';
      statusEl.style.color = '#8fda8f';
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === 'world_state') renderWorld(message.world);
    };

    ws.onclose = () => {
      statusEl.textContent = 'reconectando…';
      statusEl.style.color = '#ffcc66';
      setTimeout(connect, 1500);
    };

    ws.onerror = () => ws.close();
  }

  function renderWorld(world) {
    if (worldContainer) app.stage.removeChild(worldContainer);
    worldContainer = new PIXI.Container();
    app.stage.addChild(worldContainer);

    drawGround(world.environment?.period || 'day');
    narrationEl.textContent = world.narration?.text || '';
    versionEl.textContent = `World State v${world.version ?? '?'} · ${world.environment?.period || 'day'}`;

    for (const entity of world.entities || []) {
      if (entity.type === 'tree') drawTree(entity);
      if (entity.type === 'campfire') drawCampfire(entity);
      if (entity.type === 'human') drawHuman(entity);
    }
  }

  function drawTree(entity) {
    const c = new PIXI.Container();
    c.x = entity.position?.x ?? 200;
    c.y = entity.position?.y ?? 250;
    c.scale.set(entity.scale ?? 1);

    const trunk = new PIXI.Graphics().roundRect(-18, -10, 36, 105, 8).fill(0x6f4a2c);
    const crown = new PIXI.Graphics();
    crown.circle(0, -45, 64).fill(0x2e7d32);
    crown.circle(-42, -20, 43).fill(0x388e3c);
    crown.circle(42, -18, 45).fill(0x2f8f3a);

    c.addChild(trunk, crown);
    worldContainer.addChild(c);
  }

  function drawCampfire(entity) {
    const c = new PIXI.Container();
    c.x = entity.position?.x ?? 470;
    c.y = entity.position?.y ?? 330;
    c.scale.set(entity.scale ?? 1);

    const logs = new PIXI.Graphics();
    logs.roundRect(-42, 18, 84, 15, 7).fill(0x75452b);
    logs.rotation = 0.32;
    const logs2 = new PIXI.Graphics();
    logs2.roundRect(-42, 18, 84, 15, 7).fill(0x5f3824);
    logs2.rotation = -0.32;
    c.addChild(logs, logs2);

    if (entity.properties?.lit !== false) {
      const flame = new PIXI.Graphics();
      flame.moveTo(0, -70).bezierCurveTo(38, -28, 28, 14, 0, 22).bezierCurveTo(-30, 12, -34, -25, 0, -70).fill(0xff8a24);
      flame.moveTo(0, -42).bezierCurveTo(18, -18, 13, 8, 0, 12).bezierCurveTo(-15, 6, -16, -17, 0, -42).fill(0xffdc5e);
      c.addChild(flame);

      let phase = 0;
      app.ticker.add((ticker) => {
        if (!c.parent) return;
        phase += ticker.deltaTime * 0.08;
        flame.scale.y = 0.95 + Math.sin(phase) * 0.05;
        flame.rotation = Math.sin(phase * 0.7) * 0.025;
      });
    }

    worldContainer.addChild(c);
  }

  function drawHuman(entity) {
    const c = new PIXI.Container();
    c.x = entity.position?.x ?? 650;
    c.y = entity.position?.y ?? 320;
    c.scale.set(entity.scale ?? 1);

    const body = new PIXI.Graphics();
    body.circle(0, -62, 18).fill(0xd7aa7d);
    body.roundRect(-20, -43, 40, 62, 12).fill(0x496b8a);
    body.roundRect(-16, 15, 12, 52, 6).fill(0x2c3440);
    body.roundRect(4, 15, 12, 52, 6).fill(0x2c3440);
    c.addChild(body);
    worldContainer.addChild(c);
  }

  function bindSimulator() {
    simulatorEl.addEventListener('click', async (event) => {
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      const action = button.dataset.action;
      const buttons = simulatorEl.querySelectorAll('button');
      buttons.forEach((item) => { item.disabled = true; });
      try {
        const response = await fetch('/api/simulate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action }),
        });
        if (!response.ok) throw new Error(await response.text());
      } catch (error) {
        console.error(error);
        narrationEl.textContent = `Erro no simulator: ${error.message}`;
      } finally {
        buttons.forEach((item) => { item.disabled = false; });
      }
    });
  }

  boot().catch((err) => {
    console.error(err);
    statusEl.textContent = 'erro no renderer';
  });
})();
