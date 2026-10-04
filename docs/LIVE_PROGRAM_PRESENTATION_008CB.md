# 008CB — Live presentation in the NOV world

The live map now hides the exploration toggle and shows audience interactions
and narrator captions from the existing WebSocket stream. World-state narration
is delivered independently of the spatial observer payload. Audience events use
the same display-name and join/like/gift behavior as the old renderer; optional
text events show a bounded plain-text comment. The audience list holds four items,
expires after twelve seconds, and does not intercept controls. Narration expires
after 8–20 seconds and identical snapshots do not restart its timer.

The browser audio bridge reuses the old renderer's /audio/live.mp3 integration.
Direct viewers activate audio with its button. capture=1 leaves audio to the
existing parent monitor, avoiding duplicate playback. Neither captions nor the
audio bridge generate new narration or write world/memory state.

Validation:
- Live program Godot smoke: no failures or resource/script errors.
- NOV locomotion Godot smoke: no failures or resource/script errors.
- World-map traversal Godot smoke: no failures or resource/script errors.
- Audio and audio-web services active; public stream returned 200 audio/mpeg.

Deploy:
```bash
sudo bash /home/etbra/live.infinita/deploy/apply-live-program-008cb-root.sh
```

This exports the preview with all Godot checks, installs five presentation/feed
scripts, restarts the renderer, and promotes the ready map at /godot/. Previous
native scripts, preview files, live entrypoint and metadata are backed up and
restored on rollout failure. Output: /home/etbra/008cb-rollout.log.

The existing autonomous world, memory, audience ingestion and narration services
are reused. Synthetic UI fixtures were used only in tests, not injected into the
production audience stream.

Narrator captions are anchored at the vertical center of the scene, with
centered text, to avoid the bottom UI area of streaming applications.
