# Atmosfera física — 008DO

Esta versão acrescenta vento e nuvens ao céu de 008DN. É um modelo físico simplificado, calculado no servidor, independente dos FPS do navegador e do renderer nativo. Não contém influência da Memoria.ia sobre o clima nem aprendizagem climática de Nov.

## Estado e evolução

`world_physical_weather.py` integra passos fixos de 1 segundo do relógio lógico persistido. Temperatura relaxa conforme a insolação e cobertura; vapor condensa perto da saturação, nuvens dissipam em ar seco e uma parcela limitada evapora conforme água e insolação. Excesso de líquido é contabilizado como precipitação acumulada; chuva não é desenhada nesta versão. O vento responde a uma força analítica variável com arrasto e rajadas, limitado a 8 m/s. Seu deslocamento acumulado transporta as nuvens.

O modelo usa temperatura/clima global e a fração de regiões aquáticas, sem resolver pressão tridimensional ou meteorologia local. A invariância entre frequências de publicação pressupõe os mesmos parâmetros ambientais durante o intervalo: esta versão não reconstitui o histórico de alterações externas desses parâmetros.

O checkpoint privado `/var/lib/live-infinita/weather/state.json` permite continuar após reiniciar. Cada execução integra no máximo 600 passos e recupera atrasos em lotes. Pausar o relógio interrompe a evolução física. Um checkpoint inválido ou relógio recuado causa falha sem substituir a última projeção pública; não há reset silencioso para outro mundo.

Um serviço sem acesso à rede publica a projeção em `/var/lib/live-infinita/cognitive-terrain/weather.json` a cada aproximadamente 2 segundos. Ela integra a entrega WebSocket, inclusive durante pausa, sem modificar o WorldState autoritativo. O arquivo público contém somente valores ambientais e metadados, sem conteúdo de memórias ou credenciais.

## Apresentação

24 grupos de nuvens, com três volumes cada, usam um MultiMesh. Posições derivam da identidade do mundo e do deslocamento pelo vento. A repetição espacial ocorre além do plano distante da câmera atual, evitando reposicionamento dentro da área visível. A interpolação visual extrapola no máximo 5 segundos; projeções com mais de 180 segundos deixam de influenciar a apresentação gradualmente.

Vegetação baixa recebe deformação de shader ancorada na base, em direção ao vento global. Troncos, árvores sólidas, terreno, colliders e regras de navegação continuam com sua geometria física. Cobertura de nuvens modula suavemente a iluminação diária, preservando o preenchimento noturno.

## Validação

- 8 testes Python da atmosfera: persistência, pausa, frequência, advecção, conservação de vapor/líquido/precipitação no cenário fechado, limites e rejeição de corrupção.
- 6 testes Python do céu e 117 de navegação: 131 testes Python aprovados no total.
- 31 testes Godot headless aprovados, incluindo céu, câmera, terreno, colisões, recuperação e clima.
- Teste nativo OpenGL Compatibility com Mesa llvmpipe: 1.222 pixels mudaram entre céu limpo e nuvem; 47 entre fases de vento na vegetação. Sem erros de script ou shader. Capturas isoladas em `PHYSICAL_WEATHER_NATIVE_CLOUD_008DO.png` e `PHYSICAL_WEATHER_NATIVE_WIND_008DO.png`.
- Sintaxe dos scripts de exportação/instalação e `git diff --check` aprovados.

Os testes nativos verificam a renderização real em cenário isolado. A atualização ainda exige instalação e inspeção da live e do navegador; os resultados acima não são confirmação de produção.

## Instalação

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-physical-weather-008do-root.sh
```

Resultado esperado: `008DO_OK`. Registro: `/home/etbra/008do-renderer-rollout.log`. O instalador exige checkout limpo, guarda cópias de arquivos e unidades e restaura a versão anterior se uma etapa falhar. O checkpoint físico privado é preservado no rollback.

Depois de instalar: verificar unidades, build, projeção no WebSocket real e aparência no navegador. A próxima etapa poderá registrar observações e previsões de Nov, comparar previsão com resultado e permitir influência limitada da memória. Esta versão fornece somente a base física para isso.
