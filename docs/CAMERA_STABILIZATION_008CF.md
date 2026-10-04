# 008CF — stabilize NOV's follow camera

The attached 16.9-second recording shows large framing changes near obstacles. The previous implementation blended heading by a fixed 0.34 every frame and immediately assigned camera position; regular observer feed callbacks also advanced camera positioning. Local escape probes could therefore rotate the entire scene rapidly.

A separate camera stabilizer now waits for 0.25 seconds of a consistent heading before turning. Candidates differing by more than 36 degrees restart that hold; an 8-degree dead zone prevents small heading corrections. The camera turns at most 45 degrees per second. Exponential smoothing follows horizontal translation, height and look target, independent of FPS. NOV's collision decisions and motion animation remain separate.

Observer packets update destinations. Only first binding resets the camera; subsequent follow interpolation advances in the frame loop. Camera horizon uses world UP. Collision and ground constraints run after smoothing, so inertia cannot move the resulting eye through a wall or underground. Safety can still require immediate shortening of the camera arm; returning to an unobstructed view is damped.

Validation: camera smoke covers alternating escape probes, sustained turns, per-step rotation limits, matching 30/120 FPS, position/height damping, obstacle occlusion, ground clearance, level horizon and feed callback isolation. Existing gait, physical traversal, grounded presentation, narrator/audience, ground mesh and experiential escape smokes also run before export.

Deployment: sudo bash /home/etbra/live.infinita/deploy/apply-camera-stabilization-008cf-root.sh
Success marker: 008CF_OK. The installer backs up and exports in isolation, restarts native rendering and promotes the web entry point with rollback. It preserves the navigation memory file and does not install or restart the Memoria navigation ingestion service. Reload browser/live source after installation.
