# 008DY — não interromper um desvio apenas pela distância ao objetivo

## Problema reproduzido
O detector de aprisionamento usa a distância em linha reta ao destino. Um desvio longo ao longo de uma margem ou parede pode aumentar essa distância apesar de Nov estar avançando. Na reprodução isolada, a versão anterior acionou retorno no passo 900, com dt de 0,1 s.

Os registros de produção apresentam retornos repetidos, incluindo posições próximas a x=19. O defeito do detector foi reproduzido; ainda não se demonstrou que ele explica cada retorno registrado ou que todos correspondem ao mesmo obstáculo.

## Ajuste
O detector recebe a posição efetivamente ocupada após a movimentação física. A entrada numa célula nova de 3 m renova o prazo de 90 segundos sem progresso. Voltar a uma célula já visitada não concede esse crédito. A distância ao objetivo ainda pode renovar o prazo quando melhora pelo menos 1 m.

A detecção de confinamento por 30 segundos no raio de 2,5 m continua independente: cruzar uma fronteira de célula com pequenos movimentos não anula esse limite. O conjunto temporário é limitado a 4096 células e não sofre remoção de células antigas; isso impede que um circuito vire exploração nova após uma remoção. Com o limite cheio, só a melhoria da distância renova o prazo.

O conjunto é liberado ao chegar, parar, trocar objetivo ou reiniciar o detector. Não é promovido a conhecimento nem enviado à Memoria.ia. Não modifica o planejador por tentativa e erro, as colisões ou o World State. O compromisso de rota mantém o limite absoluto de 900 segundos. Nov não recebe conhecimento de pontes ou passagens não observadas.

O log NOV_STUCK_DETECTED passa a informar confinamento ou repetição sem progresso, tempo, quantidade de células e distância restante. Isso permitirá distinguir as causas em produção antes de outras mudanças.

## Verificação
- Reprodução anterior: retorno ao longo de um desvio a 90 s.
- Detector corrigido: 140 s de desvio sem retorno indevido.
- Movimento da cápsula real ao longo de uma parede: mais de 130 m em passos físicos, sem retorno por distância nem alteração lateral da posição.
- Circuito repetido e pequena oscilação continuam acionando recuperação.
- Teste anterior de poço físico, retorno seguro e contabilidade de jornada passou.
- Suíte completa: 38 testes Godot passaram. Teste dirigido repetido após acrescentar o caso da cápsula real.

Essa validação não comprova melhoria da navegação na produção. O próximo passo é comparar os retornos e seus novos motivos depois da instalação.

## Instalação
O instalador executa os 38 testes no export isolado, publica Web e copia apenas nov_stuck_recovery.gd ao renderer nativo. Faz backup e rollback de código e apresentação. Reinicia o renderer; uma busca ativa nesse momento será encerrada pelo mecanismo existente de reinício. Preserva memórias, encontros, animais e o histórico privado das tentativas.

```bash
sudo bash /home/etbra/apply-detour-recovery-008dy-root.sh
```

Recarregue a fonte da live após concluir. A tag e branch v0.1.0 permanecem congeladas.
