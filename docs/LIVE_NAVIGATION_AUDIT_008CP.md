# 008CP — auditoria de percursos após continuidade do terreno

## Instalação verificada

Build público: bd3630a; rollout 008CO concluído.
Renderer ativo desde 2026-10-04 20:36:13 UTC, sem reinícios automáticos
na verificação. Os scripts instalados de cena, destino, experiência e
episódios coincidem com o repositório. Saúde do runtime: ok.
A ponte registrou ingestão/recall bem-sucedidos após o rollout.

## Janela congelada

Fonte: episódios nativos retidos, validados e deduplicados.
Início: 2026-10-04T20:37:11.838780+00:00; fim: 2026-10-04T20:41:41.997700+00:00.
O JSON LIVE_NAVIGATION_RESULT_008CP.json contém o hash do snapshot,
IDs dos episódios, limites de retenção e contagem por identidade de rota.

- 851 ações concluídas: 850 passos intermediários e um destino alcançado.
- Zero colisões e zero ações interrompidas na janela.
- 15 escolhas alteradas causalmente pela RAM; todos os passos concluídos.
- Zero escolhas alteradas causalmente por Memoria.ia nessa janela.
- Duas identidades de rota, cada uma com destino constante.
- A primeira contém a chegada; a segunda ainda não contém chegada.
- Nenhuma ação sem identidade de rota.

A leitura anterior, imediatamente antes desta captura, tinha 887 ações
e os mesmos um destino, zero colisões e 15 escolhas causais da RAM.
A diferença de contagem vem da janela móvel de retenção, não de perda
demonstrada de aprendizado. Não somar capturas sobrepostas.

Os três registros promovidos observados no log são cumulativos, já
existentes, e não comprovam três novas promoções desde o rollout.
A recuperação persistente estar funcionando não significa que alterou
uma decisão nessa janela.

## Limites e próximo experimento

O registro de chegada demonstra que Nov alcançou um destino local
observado do feed. Não demonstra que o objetivo autoritativo do mundo
foi cumprido, nem que a memória reduziu o comprimento total da rota.

A retenção pode começar no meio de um percurso: a auditoria marca
full_route_coverage_proven=false mesmo quando encontra chegada.
Também informa identidades antigas ausentes e destinos inconsistentes,
e separa mundos para não misturar rotas com o mesmo identificador.

A melhoria observada sucede as atualizações 008CN e 008CO. As janelas
anteriores tinham outros percursos e terrenos; não permitem atribuir
uma redução quantitativa isolada a qualquer uma das correções.

Próximo experimento: executar percursos equivalentes com início, destino
e superfície fixos, observar o percurso completo e comparar decisões,
colisões e distância com e sem memória. A infraestrutura desta auditoria
apenas observa os registros; não altera navegação, terreno ou memória.

## Verificação e uso

66 testes Python de navegação passaram, incluindo agrupamento por mundo,
chegada sem falsa cobertura completa, inconsistência de destino e
compatibilidade com ações antigas sem identidade de rota.

Não requer instalação nem reinício de serviços.

```bash
cd /home/etbra/live.infinita
python3 tools/audit_live_navigation_008cm.py --report /home/etbra/live-navigation-audit.json
```
