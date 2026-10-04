# 008CR — logo no topo da live

Restaura a marca do broadcast antigo na cena Vale de Nov: símbolo azul,
LIVE INFINITA, subtítulo um mundo que continua e selo AO VIVO.
Desenho baseado em broadcast_overlay.gd.

A marca permanece no topo; a audiência começa abaixo dela e a legenda
permanece no centro. O desenho ajusta a escala à largura da apresentação
e ignora eventos do mouse.

Verificação: smoke existente do programa passou com zero falhas;
captura renderizada em 720 x 1280 conferida visualmente com audiência
e legenda simultâneas. Nenhuma mudança em navegação ou memória.

Aplicar na VM:

```bash
cd /home/etbra/live.infinita && git pull --ff-only && sudo bash deploy/apply-live-logo-008cr-root.sh
```

O instalador exporta Web, atualiza o renderer nativo e promove a cena
para /godot/, com backup e rollback. Confere o commit e os indicadores
de marca no build público. Sucesso: 008CR_OK.
Log: /home/etbra/008cr-renderer-rollout.log.
Depois da aplicação, recarregar a fonte da live.
