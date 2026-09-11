# MVP-008 — validação Ubuntu com Godot pausado

## 1. Checkout e testes isolados
Execute em uma sessão Bash. Este checkout separado evita trocar a branch do
diretório usado anteriormente para exportar Godot. Se a pasta já existir, confirme
que é este repositório e que está limpa antes de atualizar.

```bash
set -euo pipefail
cd "$HOME"
git clone --single-branch --branch mvp/actor-identity-state-008 \
  https://github.com/marceloroldao/live.infinita.git live.infinita-mvp008-validation
cd live.infinita-mvp008-validation
git log -1 --oneline
python3 -m venv .venv
.venv/bin/python -m pip install -r tests/requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

Esperado: 25 testes, `OK`. A suíte usa dados temporários, inclusive para commits
do runtime; não aponta para `/var/lib/live-infinita`.

## 2. Atualizar somente o backend já instalado
Pré-requisitos: instalação existente em `/opt/live.infinita`, serviço
`live-infinita` e dados em `/var/lib/live-infinita`, conforme o service do projeto.
Confira antes:

```bash
sudo systemctl cat live-infinita
curl -fsS http://127.0.0.1:8080/api/replay/verify
```

Prossiga somente com replay `ok=true` e caminhos correspondentes. Execute os
comandos abaixo no checkout da etapa 1. Não use o instalador geral nesta rodada:
ele substitui nginx e sincroniza a instalação inteira com `--delete`.

```bash
backup="/var/backups/live-infinita-mvp008-$(date +%Y%m%d-%H%M%S)"
sudo mkdir -p "$backup"
sudo systemctl stop live-infinita
sudo tar -C / -czf "$backup/before-update.tar.gz" \
  opt/live.infinita/apps var/lib/live-infinita
printf '%s\n' "$backup" | tee /tmp/live-infinita-mvp008-backup-path
sudo rsync -a --exclude '__pycache__/' \
  apps/actors apps/audience apps/gateway apps/world-runtime \
  /opt/live.infinita/apps/
sudo chown -R liveinfinita:liveinfinita \
  /opt/live.infinita/apps/actors /opt/live.infinita/apps/audience \
  /opt/live.infinita/apps/gateway /opt/live.infinita/apps/world-runtime
sudo /opt/live.infinita/.venv/bin/python -m pip install \
  -r /opt/live.infinita/apps/world-runtime/requirements.txt
sudo systemctl start live-infinita
sudo systemctl --no-pager --full status live-infinita
```

Esse procedimento preserva os arquivos do renderer/Godot, a configuração nginx e
os dados existentes. O startup acrescenta ao Actor Store as observações históricas
ainda ausentes. Se uma etapa falhar depois do stop, examine o erro e os logs antes
de continuar; o backup contém código anterior e dados anteriores à atualização.

## 3. Health, atores e replay (somente leitura)
```bash
python3 tests/validate_mvp008_vm.py
curl -fsS http://127.0.0.1:8080/api/actors | python3 -m json.tool
curl -fsS http://127.0.0.1:8080/api/replay/verify | python3 -m json.tool
```

Esperado: MVP `008`, versão `0.9.0`, replay consistente e participantes históricos
quando existirem logs recuperáveis. Uma lista vazia só é esperada sem tais logs.
Para verificar persistência e backfill idempotente sem novos eventos entrando,
anote `observations_total`, reinicie `live-infinita` e consulte novamente: o total
deve permanecer igual.

## 4. Teste com observações novas
Execute em janela sem comandos de outros produtores, pois o teste compara o mundo
antes/depois. O teste cria duas identidades identificadas por UUID e três
observações persistentes: dois joins e um comentário sem intenção reconhecida.
Pode gerar propostas pendentes conforme os contadores de audiência; não as aprova.
O HTTP 422 do comentário é esperado e sua identidade ainda deve ser observada.

```bash
python3 tests/validate_mvp008_vm.py --write
```

Esperado: `PASS` para identidade, duplicata, mudança de nome, separação entre
plataformas e mundo inalterado. Os dados de teste ficam no log append-only.
Para diagnosticar falhas:

```bash
sudo journalctl -u live-infinita -n 100 --no-pager
```

O PR deve continuar em rascunho até registrar o resultado destas etapas na VM.
