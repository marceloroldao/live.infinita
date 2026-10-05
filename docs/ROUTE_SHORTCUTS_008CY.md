# 008CY — Curvas locais mais curtas, com verificação física

Nov pode avançar para um ponto posterior do caminho já observado quando o corredor completo está livre. Isso reduz os cantos em escada da busca em grade sem depender de coordenadas conhecidas da ponte.

Cada decisão testa no máximo três corredores. Tanto a distância acumulada pelo caminho original quanto cada corredor ficam limitados a seis metros. A verificação usa a mesma cápsula, água e limite de altura por passo da execução, em segmentos de até um metro. O próximo passo de movimento continua limitado a um metro e passa também pela percepção normal. Os pontos anteriores só são descartados depois de esse passo ser aceito.

O registro de percepção inclui `observed_route_shortcut_waypoints`. A origem continua sendo percepção: encurtar uma rota calculada não é evidência de aprendizado causal da Memoria.ia. Não há alteração na câmera, velocidade, objetivos do feed ou escrita no World State.

## Validação

O teste `godot_route_shortcuts_008cy_smoke.gd` compara duas execuções físicas idênticas, desativando somente os atalhos no controle. Na ponte próxima, o controle percorreu 109,5273 m e o tratamento 102,6248 m (6,30% menos). Ambos chegaram, sem colisões ou entrada na água. O tratamento executou atalhos em 144 quadros de movimento.

Há verificações de canto livre, canto bloqueado por corpo sólido, água, terreno íngreme, limite de três consultas e preservação dos pontos antes da aceitação. A comparação mede esta geometria; não demonstra a menor rota possível nem ganho universal no mundo da live. Os vinte testes Godot da suíte de publicação passaram com código de saída zero e sem erros de script, incluindo a travessia distante 008CX e o contato de câmera 008CW.

## Instalação

No servidor:

```bash
cd /home/etbra/live.infinita
git pull --ff-only
sudo bash deploy/apply-route-shortcuts-008cy-root.sh
```

O instalador valida e exporta uma cópia isolada antes de trocar os arquivos da live, mantém backup e restaura os arquivos anteriores em caso de erro. O resultado fica em `/home/etbra/008cy-renderer-rollout.log`. A confirmação final é `008CY_OK`, além de `008CY_PUBLIC_OK` com o commit publicado.

A preparação e o envio ao GitHub não instalam a versão em produção. Após executar, verificar os marcadores, o commit público, o serviço e novos percursos nativos.
