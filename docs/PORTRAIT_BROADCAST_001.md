# Portrait Broadcast 001 — Live.infinita

## Goal

Make the primary program feed native vertical video instead of cropping a landscape composition.

## Program canvas

- 720x1280
- 9:16 portrait
- 30 fps
- H.264/yuv420p on the internal video bus
- audio remains independent on UDP :5500
- video remains on UDP :5600

## Composition zones

1. Brand/live status: compact top band.
2. Audience activity: top safe region, transient and translucent.
3. World stage: dominant central region; entities remain the visual protagonist.
4. Narration: lower safe region with multiline cinematic caption.
5. Platform UI safety: outer margins intentionally kept free of critical content.

The native server broadcaster never renders development guides. Browser preview may opt into guides with `?guides=1`.

## Principle

Portrait is not a crop of the desktop scene. It is a first-class camera/composition profile for mobile live platforms. World State remains presentation-agnostic.

## Future

- camera framing driven by entity salience
- dynamic safe-area profiles per destination platform
- 1080x1920 quality profile after server load measurements
- event-aware focus and cinematic transitions
