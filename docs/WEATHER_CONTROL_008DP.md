# Controle prospectivo de previsões — 008DP

008DO foi confirmada instalada em produção, commit `bd44305`: rollout `008DO_OK`, runtime e renderer ativos, timer físico ativo. O WebSocket real entregou o mesmo mundo com tempos físicos 605861000 → 605864000 ms, vento e cobertura de nuvens variando. Esta verificação confirma a entrega/evolução dos dados, sem substituir a inspeção visual pelo usuário.

008DP acrescenta uma referência prospectiva para o próximo teste da Memoria.ia. Ainda não é uma previsão de Nov: o método de controle simplesmente prevê que os valores atuais permanecerão iguais durante os próximos 60 segundos lógicos. Nenhuma inferência ou memória é usada e nenhuma regra física é alterada.

## Protocolo

1. Ler uma projeção física válida, recente e do mundo atual.
2. Persistir uma previsão para `tempo_atual + 60000 ms`, com valores, método, identidade do mundo, duração de tick, horário de emissão e SHA-256 do registro.
3. Quando uma observação real alcançar o alvo, comparar seus valores com a previsão que já estava no disco. A tolerância é de até 5000 ms depois do alvo e o horário observado real é preservado.
4. Se a coleta chegar além da tolerância, marcar a tentativa como perdida. Não interpolar observações, preencher lacunas ou avaliar contra um alvo diferente.
5. Emitir a próxima previsão somente a partir dessa nova observação.

A pausa do relógio não duplica previsões nem avaliações. Reiniciar retoma a previsão pendente. Uma coleta repetida no mesmo tempo lógico não reconta o resultado. Recuo de relógio, troca de mundo/duração, entrada corrompida ou previsão modificada são rejeitados.

Cada erro é medido em sua unidade: temperatura em °C, umidade e cobertura em frações de 0 a 1, componentes e erro vetorial do vento em m/s. As médias são `null` enquanto não houver avaliação; zero não significa ausência de dados. O registro retém até 512 avaliações com previsão e observação; contagens e somas cumulativas continuam após a retenção. SHA-256 verifica integridade, não fornece autenticação contra alteração deliberada de todos os registros.

Checkpoint privado: `/var/lib/live-infinita/weather/control.json`, modo 0600. Projeção pública: `/var/www/live-infinita-godot/navigation-memory/weather-control.json`, modo 0644. Serviço sem credenciais e sem rede; grava somente controle e status. Não abre o banco da Memoria.ia nem modifica WorldState, clima, renderer ou navegação.

## Validação

Oito testes específicos cobrem emissão anterior ao resultado, pausa/repetição, perda da janela, limite da tolerância, rejeição de recuos/corrupção, reinício, arquivos privados/públicos, fontes desatualizadas e retenção sem perder métricas cumulativas. Mais oito testes de regressão da atmosfera passaram.

A prova de integração usa exclusivamente projeções recebidas do WebSocket real, checkpoint isolado temporário e emissão/avaliação separadas no tempo. Seu registro está em `WEATHER_CONTROL_LIVE_LOG_008DP.txt`. O teste não instala o serviço nem modifica dados da live. A tentativa emitida em 606056000 ms foi avaliada exatamente em 606116000 ms: uma avaliação, nenhuma janela perdida, erro vetorial do vento de 0,425477 m/s e erro de temperatura de 0,223358 °C. Uma amostra comprova o funcionamento do controle, sem permitir concluir desempenho preditivo ou aprendizagem.

## Instalação

Pré-requisito: 008DO instalada e timer físico ativo.

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-weather-control-008dp-root.sh
```

Sucesso: `008DP_OK`. Log: `/home/etbra/008dp-weather-control-rollout.log`. O instalador guarda a versão anterior dos arquivos e unidades e executa rollback se uma etapa falhar. Preserva o checkpoint privado para não apagar previsões já emitidas. O build visual continua sendo o de 008DO; este rollout acrescenta somente o controle de teste no servidor, sem nova exportação Godot.

Status acessível em `https://live.etbra.com.br/godot/navigation-memory/weather-control.json`. A primeira avaliação exige pelo menos 60 segundos lógicos avançados. Na próxima etapa, previsões com memórias realmente recuperadas deverão ser emitidas antes do resultado e comparadas ao controle no mesmo alvo e com a mesma observação. Ganho só poderá ser medido depois desse teste pareado; métricas deste controle não são aprendizagem da Memoria.ia.
