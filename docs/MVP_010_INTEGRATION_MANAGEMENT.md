# MVP-010 — gerência de integrações

Painel inicial em `/manage/` para configurar OpenAI e TikTok Live sem editar
arquivos manualmente. A mesma chave de operador do MVP-009 desbloqueia o painel.

## OpenAI

- Salva a API key e o modelo escolhido no servidor.
- Testa a chave consultando `GET https://api.openai.com/v1/models` com Bearer.
- A chave completa nunca aparece em respostas, health, HTML ou logs da aplicação.
- O padrão inicial é `gpt-5-mini`; salvar a chave ainda não coloca a LLM no fluxo
  crítico. A integração com o AI Router será uma evolução posterior.

A API oficial orienta manter API keys fora do código do navegador e carregá-las
no servidor por variável de ambiente ou serviço de segredos. Este MVP usa arquivo
servidor com permissão 600, adequado à VM única atual.

## TikTok Live

- Salva `@usuario` da live.
- Aceita opcionalmente a chave de assinatura Euler Stream usada pela biblioteca
  TikTokLive para aumentar limites.
- Não coleta `sessionid` da conta TikTok. Esse cookie dá acesso amplo à conta e a
  própria biblioteca exige uma liberação explícita antes de enviá-lo ao assinador.
- Alterar o arquivo reinicia automaticamente o serviço do conector. Se a live
  estiver offline, o serviço continuará tentando conforme a regra existente.

## Segurança e armazenamento

- `/manage/` contém somente a interface. Ler ou gravar configuração exige
  `Authorization: Bearer <chave-do-operador>`.
- O navegador mantém a chave do operador apenas em `sessionStorage`; fechar a aba
  encerra essa sessão de gerência.
- Segredos ficam em `/var/lib/live-infinita/integrations.json`, modo 600 e usuário
  `liveinfinita`. A API retorna somente estado e quatro caracteres finais.
- Campo secreto vazio remove a chave; campo omitido mantém a chave atual.
- A chave compartilhada é uma solução transitória para uma VM. Não oferece contas,
  perfis, trilha por operador, criptografia independente ou recuperação de senha.

Para obter a chave de gerência no terminal da VM:

```bash
sudo sed -n 's/^LIVE_INFINITA_OPERATOR_TOKEN=//p' /etc/live-infinita/operator.env
```

Cole-a no primeiro campo de `https://live.etbra.com.br/manage/`. Não envie essa
chave em mensagens e não a coloque em screenshots.

## Validação

```bash
python3 -m unittest discover -s tests -v
python3 tests/validate_mvp010_vm.py
python3 tests/validate_mvp010_vm.py --base-url https://live.etbra.com.br
```

O verificador é somente leitura e confirma página, autenticação, health e replay.

## Validação pré-instalação — 2026-09-11

- 39 testes passaram no Windows/Python 3.11 e no Ubuntu/Python 3.14.
- Servidor isolado na VM: página, proteção, gravação com valores fictícios,
  mascaramento, persistência após reinício, mundo inalterado e replay passaram.
- O conector TikTok carregou usuário e chave de assinatura fictícios do arquivo
  gerenciado, sem realizar conexão externa.
- Sintaxe dos scripts de instalação e recarga validada no Ubuntu.
- Nenhuma chave real foi usada durante os testes.

## Produção — 2026-09-11

- Instalador executado pelo operador; backup em
  `/var/backups/live-infinita-mvp010.kRT9Ct`.
- Serviço principal e monitor de configurações ativos.
- Hashes de `main.py` e do conector TikTok conferidos após a instalação.
- Validação passou pelo endereço local e por `https://live.etbra.com.br`.
- Gerência online com OpenAI e TikTok ainda não configurados; o arquivo de
  integrações será criado somente no primeiro salvamento.
- Chave de operador em `/etc/live-infinita/operator.env`, `root:root`, modo 600.
- Mundo preservado: 192 eventos, 192 deltas, versão 193, sequência 192, com hash
  atual e replay iguais a
  `12770f39d4cb81a9e7b926168910e0e5160798c55f93bc352595def74051b8c7`.
- Nginx, Godot e segredos existentes foram preservados.
