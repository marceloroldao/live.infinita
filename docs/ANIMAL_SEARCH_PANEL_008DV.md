# 008DV — resultados da busca de animais no painel da live

Acrescenta duas linhas ao painel existente de tentativa e erro:
- `Animais: N lembrados | R regiões`: encontros confirmados pela ponte Memoria.ia e previsões cujo horizonte ainda está válido.
- `Acertos: memória A/P | último B/P`: resultados medidos sobre os mesmos P novos avistamentos, comparando a região por recorrência com o último local visto.

Enquanto não há pares, mostra espera por avistamento, confirmação ou novos encontros. Não apresenta 0/0 como precisão. Uma previsão cujo horizonte acabou, mas aguarda ACK, não conta como região ativa.

## Origem e limites
O novo `nov_animal_search_panel.gd` lê exclusivamente as projeções públicas `encounter-memory.json` e `search-predictions.json`, sem autoridade para mover Nov. Números continuam vindo da ponte 008DT e do previsor 008DU.

Na Web, usa URLs absolutas da origem atual, duas requisições independentes a cada cinco segundos, timeout de quatro segundos e limite de 128 KiB por resposta. No renderer nativo, lê os mesmos arquivos públicos.

Exige mundo igual ao contexto atual de Nov, schema correto, ausência de erro, publicação com até 60 segundos, autoridade de escrita falsa e decisão de busca ainda desativada. Rejeita timestamps futuros, respostas fora de ordem, contadores inconsistentes e previsões emitidas no futuro lógico. Troca de mundo limpa o cache; dados vencidos deixam de mostrar números atuais. A prévia offline não consulta nem apresenta resultados do servidor.

A interface descarta coordenadas e registros completos após calcular os resumos. Não acessa posições globais dos animais, estado privado, API de memória ou credenciais. Não injeta previsão como experiência, não altera a física nem o modelo da memória.

## Apresentação
Mantém os contadores de caminhada, a distinção RAM/Memoria.ia, o logo, audiência e narrador. Reduz a fonte do painel de 16 para 15 e o espaçamento entre linhas para acomodar os resultados sem cobrir a legenda central nas capturas verificadas. Explorar permanece oculto.

Capturas de revisão em 720x1280 e 1280x720 usam resultados reais publicados pelo previsor e uma cena de apresentação isolada, com narração de exemplo e caminhada pausada. Não são capturas de uma instalação 008DV em produção.

## Validação
- Suite completa: **36 testes Godot passaram**.
- Teste adicional do painel por HTTP real contra servidor local com fixtures: zero falhas.
- Verificação visual nas duas orientações, incluindo texto, marca e legenda.
- Sintaxe dos instaladores e exportador verificada.

Na amostra de produção capturada durante o desenvolvimento, havia 21 encontros lembrados e três comparações: memória 2/3 e último local 2/3. A distância média era aproximadamente 7,60 m para a região por memória e 4,38 m para o último local. Portanto esta amostra não demonstra vantagem da previsão por recorrência. Esses números são registros daquele instante; a avaliação continua no servidor.

Evidências: `ANIMAL_SEARCH_PANEL_RESULT_008DV.json`, logs de validação e imagens `animal-search-panel-008dv-portrait.png` e `animal-search-panel-008dv-landscape.png`.

## Aplicação
Requer 008DU instalada. O instalador faz backup/rollback dos três scripts nativos alterados e do export Web, executa todos os smokes e publica o novo build. Reinicia o renderer para entregar o HUD nativo, preservando população, outbox, ACKs e memórias. Os timers de memória e previsão continuam ativos.

```bash
sudo bash /home/etbra/apply-animal-search-panel-008dv-root.sh
```

Depois, recarregue a fonte da live em https://live.etbra.com.br/godot/ . A tag e a branch `release/v0.1.0` permanecem no commit congelado. O previsor continua em avaliação, com `decision_use=false`; busca dirigida pela previsão e caça não fazem parte desta atualização.
