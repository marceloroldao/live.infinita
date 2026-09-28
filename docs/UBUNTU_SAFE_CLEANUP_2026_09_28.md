# Ubuntu da VM Live.infinita — limpeza segura (28/09/2026)

VM: Ubuntu 26.04 LTS, KVM, ~4,2 GiB RAM, disco root de 28 GiB.
É um servidor de produção: rede, SSH, Nginx, TLS, Git/Node/Remote Desktop,
renderização Godot/FFmpeg e Single Writer devem continuar operando.

## Remoções de usuário já executadas

- Removidos via git worktree remove 14 worktrees limpos antigos de testes em
  /tmp; branches/commits permanecem no repositório. Uso do tmpfs caiu de
  875 MB para 165 MB (~710 MB liberados).
- PRESERVADO /tmp/live-infinita-perf-check: contém alteração local não
  incorporada em deploy/reload-integrations.sh.
- Limpeza de cache de downloads pip (~13 MB) e npm (~100 MB).
- PRESERVADOS ~/.npm/_npx (Remote Desktop Commander ativo), cache dos
  navegadores Puppeteer e dados das operações do usuário.

## Ação privilegiada em comando único

Execute como etbra, sem prefixo sudo:
  ~/cleanup-live-ubuntu.sh

O script versionado deploy/ubuntu-safe-cleanup.sh realiza:
1. Preflight do Single Writer, API, swap e shadow sem escrita.
2. Backup protegido dos logs kernel/OOM e da unidade autoritativa.
3. Limite persistente do journal a 200 MB e 14 dias; rotate/vacuum após backup.
4. apt-get clean (somente downloads; não desinstala pacotes).
5. Exclui ZIP da engine Godot se binário e export web estão instalados.
6. Exclui TPZ dos templates somente se arquivos instalados em /root/.../4.7.2.stable
   estiverem presentes; caso contrário, PRESERVA o download.
7. Verifica serviços, health e gate social após a limpeza.

Não toca nos arquivos de replay, banco, eventos, /var/lib/live-infinita,
swapfile, engine em /opt, templates instalados, build público,
credenciais ou configuração da rede.

## Serviços e pacotes que permanecem

Nginx, SSH, systemd-networkd/resolved, chrony, unattended-upgrades,
Live.infinita, renderizador, Godot, FFmpeg e ferramentas da conexão remota
ficam inalterados. ModemManager identificou nenhum modem; snap list mostrou
nenhum Snap instalado. Os serviços podem ser desabilitados reversivelmente
num passo posterior, após preflight próprio, mas não são removidos agora.

A simulação de purge em lote para modemmanager, multipath-tools, fwupd,
udisks2, upower e snapd também selecionou ubuntu-server e
ubuntu-server-minimal. Não usar esse comando em produção.
Multipathd merece verificação como root antes de qualquer desabilitação:
a raiz usa LVM, e o diagnóstico sem root retornou permissão negada.

Para rollback do limite do journal: remover
/etc/systemd/journald.conf.d/90-live-infinita-retention.conf e reiniciar
systemd-journald. Backups dos logs ficam sob
/var/backups/live-infinita/ubuntu-safe-clean-<timestamp>/.
Os caches baixados podem ser recuperados pelo gerenciador de pacotes ou
instalador Godot, caso necessários futuramente.
