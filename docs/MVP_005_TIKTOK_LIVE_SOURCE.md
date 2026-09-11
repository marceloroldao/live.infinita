# MVP-005 — TikTok Live Source Bridge

Objetivo: conectar uma fonte TikTok Live real ao pipeline já validado sem acoplar TikTok ao runtime determinístico.

## Arquitetura

```text
TikTok LIVE
   |
   v
TikTokLive bridge (processo separado)
   |
   v
POST /api/source/tiktok/event
   |
   v
UniversalEventEnvelope v1.0
   |
   v
Intent -> Validator -> Deterministic Runtime
   |
   v
Event + Delta -> World State -> WebSocket -> Renderer
```

O bridge é isolado em `live-infinita-tiktok.service`. Uma falha do TikTok ou da biblioteca de transporte não derruba `live-infinita.service`.

## Dependência externa

O protótipo usa `TikTokLive==7.0.1`, biblioteca Python de terceiros que recebe eventos de TikTok LIVE. Ela não é uma API oficial do TikTok e não deve ser considerada uma garantia de compatibilidade futura. Por isso fica confinada à camada de Source Bridge.

## Instalação do MVP-005

```bash
cd ~/live.infinita
git fetch origin
git checkout mvp/tiktok-live-source-005
git pull
sudo bash deploy/install-ubuntu.sh
```

O runtime sobe normalmente sem instalar/ativar o bridge TikTok.

## Testes sem TikTok

```bash
curl http://127.0.0.1:8080/api/health
python3 -m unittest tests/test_mvp005_tiktok_mapping.py -v
curl http://127.0.0.1:8080/api/replay/verify
```

## Configurar uma conta TikTok

Quando soubermos o `@unique_id` da conta que estará em LIVE:

```bash
sudo bash deploy/configure-tiktok.sh @SEU_USUARIO
```

Esse comando:

1. instala a dependência opcional `TikTokLive` no venv do Live Infinita;
2. grava `/etc/live-infinita/tiktok.env`;
3. instala e habilita `live-infinita-tiktok.service`;
4. aponta o bridge para `http://127.0.0.1:8080/api/source/tiktok/event`.

## Operação

```bash
systemctl status live-infinita-tiktok --no-pager
journalctl -u live-infinita-tiktok -f
```

Ao conectar, o log deve mostrar o `room_id`. Cada comentário recebido é convertido em:

```json
{
  "source_event_id": "...",
  "actor_id": "viewer-id",
  "display_name": "Viewer",
  "text": "noite",
  "metadata": {
    "event_type": "comment",
    "room_id": "...",
    "bridge": "TikTokLive"
  }
}
```

O payload entra pelo mesmo endpoint e pelo mesmo `UniversalEventEnvelope` já testado no MVP-004.

## Primeiro teste real

Com a conta em LIVE e o bridge conectado:

1. abrir o preview do Live Infinita;
2. enviar no chat da Live o comentário `noite`;
3. confirmar no journal que o comentário chegou;
4. confirmar que o Gateway respondeu `accepted=True`;
5. observar a cena mudar para noite;
6. enviar `dia` e confirmar retorno ao dia;
7. executar `curl http://127.0.0.1:8080/api/replay/verify` e exigir `ok=true`.

## Limites desta etapa

- somente comentários de texto são encaminhados ao mundo;
- gifts, likes, follows e joins ainda não alteram o estado;
- não há LLM ou interpretação probabilística;
- comentários não reconhecidos continuam rejeitados antes do runtime;
- não há envio de mensagens de volta para o TikTok;
- o bridge é uma integração experimental de leitura.

## Critério de validação

O MVP-005 estará validado quando um comentário real de uma TikTok LIVE atravessar:

```text
TikTok -> bridge -> envelope -> intent -> validator -> runtime -> delta -> renderer
```

com proveniência `source=tiktok` e replay determinístico final `ok=true`.
