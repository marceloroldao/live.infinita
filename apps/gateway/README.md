# Gateway

Responsável por ingestão e normalização de eventos externos.

## Adapters previstos

- `simulator`
- `youtube`
- `tiktok`

## Saída

Todo evento externo deve ser convertido para um contrato interno comum antes de seguir para filtros e agregação.

O MVP deve começar pelo `simulator`, permitindo replay determinístico sem depender de uma Live real.
