# MVP-009 — participante e personagem

Primeira versão: o operador associa um participante observado a um personagem
humano já existente. Um participante tem no máximo um personagem; um personagem
tem no máximo um participante, inclusive entre fontes diferentes.

O vínculo não cria personagem, não muda o World State e não concede execução de
comandos. Não há fusão entre plataformas, login de participantes ou seleção
automática. Godot permanece em pausa.

## Contrato

- `GET /api/actors` e `GET /api/actors/{source}/{actor_id}` incluem `entity_id` e
  `binding_status`: `unbound`, `active` ou `missing_entity`.
- `GET /api/actors/{source}/{actor_id}/bindings` consulta o histórico.
- `PUT /api/actors/{source}/{actor_id}/entity` associa o ator, com JSON
  `{"entity_id":"person_01"}`.
- `DELETE` no mesmo caminho, com o mesmo JSON, desfaz apenas aquele vínculo.
- PUT/DELETE exigem `Authorization: Bearer <chave-do-operador>`.
- Repetir uma operação que já corresponde ao estado atual retorna `changed=false`
  sem acrescentar histórico. Isso não é deduplicação de requisições antigas após
  outras mudanças: o comando expressa o estado desejado no momento da execução.
- Um vínculo conflitante retorna 409; ator/personagem inexistente retorna 404;
  entidade não humana retorna 422. Para trocar, desvincule primeiro.
- Sem chave configurada, alterações retornam 503; chave ausente/incorreta retorna
  401. A proteção cobre os novos endpoints de vínculo, não modifica os endpoints
  existentes do Gateway/audiência.

## Persistência

`/var/lib/live-infinita/actor-bindings.jsonl` é append-only, separado das
observações e dos eventos do mundo. Cada registro guarda operação, ator,
personagem, horário e proveniência `operator-api/shared-token`. A chave é
compartilhada pelo operador nesta versão; não representa auditoria por usuário.

O runtime usa um único worker; escrita é serializada com os locks do runtime.
Se reset remover o personagem, a associação permanece e aparece como
`missing_entity`. Pode ser desfeita mesmo sem o personagem. Se o mesmo ID humano
voltar, o vínculo volta a aparecer como ativo. Não há controle de personagens
por chat nesta versão.

## Uso na VM

Após instalar, consulte os IDs existentes:

```bash
python3 /opt/live.infinita/deploy/manage-actor.py actors
python3 /opt/live.infinita/deploy/manage-actor.py characters
```

Exemplo (substitua `tiktok alice person_01` pelos IDs existentes):

```bash
sudo python3 /opt/live.infinita/deploy/manage-actor.py bind tiktok alice person_01
sudo python3 /opt/live.infinita/deploy/manage-actor.py unbind tiktok alice person_01
```

O helper lê a chave local sem exibi-la. Se a lista de personagens estiver vazia,
é necessário criar um visitante pelo fluxo de mundo já existente antes de vincular.
O vínculo sozinho não cria esse visitante.

## Instalação e verificação

`sudo bash deploy/update-mvp009.sh` atualiza a instalação MVP-008 validada,
com backup e rollback do código/configuração se a verificação falhar. Ele gera
uma chave local em `/etc/live-infinita/operator.env` (root, modo 600) e configura
um drop-in systemd para carregá-la. Não exibe a chave, não muda nginx, renderer,
Godot ou o arquivo principal do serviço. A chave autoriza apenas as operações
de vínculo; não concede sudo.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r tests/requirements.txt
.venv/bin/python -m unittest discover -s tests -v
python3 tests/validate_mvp009_vm.py
```

Testes de vínculo usam dados temporários, incluindo o personagem de teste.
A verificação de produção não cria observações nem executa ações do mundo.

## Validação pré-instalação — 2026-09-11

- 33 testes passaram no Windows/Python 3.11 e no Ubuntu/Python 3.14.
- Servidor HTTP isolado na VM: vínculo, reinício real do processo, persistência,
  repetição sem duplicar, desvínculo e replay passaram.
- O teste confirmou mundo inalterado entre vincular e desvincular, e HTTP 401
  para tentativa de vínculo sem chave.
- Sintaxe Bash e hashes dos arquivos do instalador foram conferidos na VM.
- Instalação no serviço de produção concluída; resultado abaixo.

## Produção — 2026-09-11

- Instalador executado pelo operador; backup em
  `/var/backups/live-infinita-mvp009.SpHEGr`.
- Serviço `live-infinita` ativo; hashes de `main.py`, `bindings.py` e do helper
  conferidos por SSH e correspondentes à implementação `cd5ceb7`.
- `validate_mvp009_vm.py`: PASS pelo endereço local e por
  `https://live.etbra.com.br`, incluindo recusa HTTP 401 sem chave de operador.
- 37 atores, nenhum vínculo criado; `person_01` (Visitante) está disponível.
- Mundo preservado: 192 eventos, 192 deltas, versão 193, sequência 192.
- Hash atual e replay iguais:
  `12770f39d4cb81a9e7b926168910e0e5160798c55f93bc352595def74051b8c7`.
- Esta conferência não criou vínculos nem ações no mundo de produção. O ciclo de
  vínculo, reinício e desvínculo foi validado no servidor isolado da VM.
- Nginx e Godot preservados pelo instalador.
