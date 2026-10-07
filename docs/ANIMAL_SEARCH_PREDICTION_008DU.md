# 008DU — regiões de busca por recorrência de encontros lembrados

Implementa a próxima camada sobre a 008DT: prever uma região onde Nov pode voltar a encontrar um coelho, usando somente encontros que a ponte já armazenou e recuperou pela API real da Memoria.ia. A tag e a branch de release v0.1.0 permanecem intactas.

## Autoridade e origem
O modelo é da aplicação: recorrência espacial, idade da evidência e proximidade da fase do dia. O núcleo Memoria.ia permanece fixado em `dfd87c995b50c49b45a9d5dd4c43cce456983d4f`, sem alteração de algoritmo.

Entradas privadas: `wildlife/encounters.json`, `wildlife/encounters-ack.json` e a identidade do mundo. O ACK é validado por checksum, mundo, sessão, cursor e identidade estrutural recalculada de cada encontro. A janela disponível é o cache dos **últimos 16 encontros efetivamente recuperados**; não há uma nova consulta histórica ampla nesta etapa.

O previsor não lê `wildlife/state.json`, habitat, necessidades, destinos dos animais ou posições globais. Não envia previsões ao núcleo nem escreve nos registros de observações. Seu serviço não recebe credenciais e tem rede desabilitada.

## Modelo limitado e auditável
- Agrupa o último local visto em células de 8 m, separadamente por animal.
- Exige pelo menos três encontros temporalmente separados na mesma célula. A separação mínima é 30 segundos lógicos após o fim do contato anterior. Uma cadeia contínua de contatos, divisões de janela e oscilações de visibilidade não aumenta esse suporte.
- Número de frames do mesmo encontro não aumenta o número de visitas.
- Descarta evidências com mais de seis ciclos de dia/noite. Usa decaimento de idade e proximidade circular de fase no ciclo de 60 minutos lógicos.
- O escore ordena regiões; **não é uma probabilidade calibrada**, nem prova de que o animal tem um hábito.
- Publica uma região por animal, com raio de 8 m e horizonte de 60 segundos lógicos, incluindo os IDs de memória usados.
- Mantém uma previsão pendente por animal; espera avaliação ou expiração antes de emitir outra. Limite de 16 previsões e 32 avaliações recentes.

A separação temporal é um critério operacional de recorrência, não uma garantia de independência estatística. Com poucos encontros, a saída correta é aguardar mais evidência.

## Avaliação prospectiva
A previsão é gravada antes do próximo encontro. Ela só pode ser avaliada por um encontro do mesmo animal **iniciado depois da emissão**, dentro do horizonte. Encontros já ocorridos que chegam com ACK atrasado não viram validação futura.

Compara, sobre o mesmo novo avistamento:
1. Distância até o centro da região prevista pela recorrência.
2. Distância até o último local visto, usado como referência de persistência.

Ambos usam o mesmo raio de acerto. Publica contagem de pares, acertos e distância média. Há tolerância de 180 segundos lógicos para chegada do ACK. Uma previsão expirada sem avistamento não conta como erro nem como prova de ausência. A janela de memória limitada pode perder avaliações com atrasos maiores; não são inventadas observações.

Estado e contadores têm checkpoint atômico privado com checksum. Reexecução no mesmo tick e reinício não duplicam emissão ou avaliação; corrupção, troca de mundo/sessão e retrocesso do relógio bloqueiam o previsor preservando o estado.

## Publicação e implantação
- Privado, 0600: `/var/lib/live-infinita/wildlife/search-predictions.json`.
- Público, 0644: `/var/www/live-infinita-godot/wildlife/search-predictions.json`.
- URL após instalação: https://live.etbra.com.br/godot/wildlife/search-predictions.json
- Serviço: `live-infinita-animal-search.service`; timer a cada 5 segundos após terminar a execução anterior.
- Instalador: `deploy/apply-animal-search-prediction-008du-root.sh`.

A instalação requer 008DT ativa e tem backup/rollback dos arquivos desta camada. Não reinicia o Godot, não altera o export Web, não apaga memórias nem modifica a população.

Para aplicar na VM existente:
```bash
sudo bash /home/etbra/apply-animal-search-prediction-008du-root.sh
```

O instalador confirma publicação fresca e sem erro. Se ainda não houver recorrência, `waiting_for_independent_encounters` é válido. Esta etapa mantém `decision_use=false`; painel visual, caminhada dirigida para uma busca e caça ficam para a próxima atualização.

## Validação
**37 testes Python passaram:** 22 da previsão e 15 de regressão da ponte 008DT. Incluem integração com a API real do núcleo congelado em SQLite isolado, aquisição prospectiva, repetição após reinício, contatos contínuos, timestamps inválidos, checksum, IDs de memória e comparações nas quais a recorrência ganha ou perde para a persistência.

O smoke Godot do sensor físico de encontros foi reexecutado para gerar uma fixture fresca usada pelo teste da ponte. Nenhuma experiência artificial foi inserida na produção.

A revisão de dados reais já publicados encontrou **12 encontros armazenados e recuperados**, com suporte para regiões de três coelhos no snapshot. Isso é uma revisão de entrada em modo somente leitura, não confirmação de serviço instalado nem evidência de melhora de navegação. Evidências: `ANIMAL_SEARCH_RESULT_008DU.json`, `ANIMAL_SEARCH_008DU_python-validation.txt` e `ANIMAL_SEARCH_008DU_godot-encounter.txt`.

## Próxima etapa
Após acumular avaliações reais, conectar uma busca limitada à intenção de Nov: previsão propõe uma região, o controlador físico revalida o caminho, o sensor confirma o encontro e os resultados alimentam a avaliação. Predição permanece distinta do que foi realmente observado.
