# 008FA — preferência por sucessos após falhas, integrada ao motor nativo

A avaliação anterior recusava recomendar quando uma das duas alternativas só tinha falhas. Isso bloqueava o uso da outra alternativa mesmo após duas saídas físicas bem-sucedidas. A regra experimental 008EY/008EZ foi integrada ao próprio `nov_navigation_patterns.gd`, com configuração reversível e desligada por padrão.

## Regra e preservação

`LIVE_INFINITA_NAVIGATION_FAILURE_PREFERENCE=1` permite recomendar a única alternativa com pelo menos dois sucessos observados quando a outra só tem falhas. Ambas continuam exigindo pelo menos duas amostras, e o custo precisa superar a margem de 20% existente. A penalidade de erro permanece 20 vezes a fração de falhas; não há novo peso calibrado.

Com a opção desligada, a avaliação anterior permanece. Evidência fraca, um único sucesso ou duas alternativas sem sucesso continuam sem preferência. Não há direção fixa, coordenadas absolutas, proibição permanente ou leitura da geometria da armadilha pelo avaliador.

A janela de aumento de custo 008ER continua permitindo novas tentativas após mudanças observadas. Nenhuma experiência é apagada para corrigir a preferência. O esquema v2, perfil localexit-v3, validação física, coletor e armazenamento existente permanecem compatíveis; não há migração ou reinício do banco.

O status nativo expõe `failure_preference_enabled`. O manifesto público declara disponibilidade da capacidade e autoridade `native_renderer_configured`; a opção efetivamente ativa deve ser verificada no status do renderer.

## Evidência integrada

O runner 008FA usa o cenário físico 008EZ, mas desativa a substituição experimental 008EY. Apenas o motor nativo com a nova opção toma as decisões. As opções anteriores de aumento de custo, continuidade e direção de saída permanecem ligadas em ambos os braços.

| Medida | Percepção | Memória integrada |
|---|---:|---:|
| Tentativas | 46 | 46 |
| Chegadas | 21 | 38 |
| Falhas reais pelo watchdog | 25 | 8 |
| Distância de todas as tentativas | 11428,11 m | 5858,68 m |
| Tempo simulado de movimento | 3428,1 s | 1757,0 s |

Foram 92 trajetórias físicas, com zero colisões e zero construções de rota global. Os resultados reproduzem os totais do experimento 008EZ. Foram persistidos 46 fatos físicos no SDK SQLite estrito e recuperados após reabertura do serviço e exclusão do cache, sem reingestão. O validador independente compara cada fato recuperado ao original, retirando apenas o identificador atribuído pelo core.

Em cada uma das três inversões, a preferência antiga inicialmente falhou; seguiram três escolhas de exploração, e a partir da quinta tentativa a alternativa corrigida chegou em todas as oito restantes. Na fase em que a percepção já acertava, a memória teve duas falhas adicionais: a adaptação tem custo e não prevê uma mudança ainda não observada. Na última recuperação com RAM vazia, a preferência corrigida veio de identificadores reais recuperados do core.

O core armazena e devolve observações; o avaliador nativo infere a preferência. O teste cobre uma família construída e determinística de armadilhas, com controle por percepção. Não compara todo o desempenho à política de memória anteriormente implantada, não demonstra transferência semântica geral e não estabelece melhoria da produção. As distâncias incluem tentativas incompletas; não são porcentagem de eficiência de rotas concluídas. O tempo exclui CPU, banco, rede e armazenamento.

## Regressões e reprodução

O exportador inclui 50 testes, executados com a nova opção ligada e desligada: 100 execuções aprovadas. O novo teste compara a integração à regra experimental com os mesmos oito fatos reais 008EY, preserva decisões dos três contextos reais 008EX, verifica abstenção com um único sucesso, opção desligada, avaliador desabilitado e margem insuficiente. A pequena matriz de margem é contrato numérico, não evidência física nem fato ingerido.

Arquivos brutos, fatos originais, recuperações, relatórios dos dois modos e validação independente estão em `docs/FAILURE_PREFERENCE_008FA/`. O nome interno `TRAP_CHANGES_008EZ.json` é mantido para compatibilidade com o runner físico reutilizado; contém `native_failure_preference=true` e `experimental_policy=false`.

Após sincronizar o projeto de teste com `apps/renderer-godot`:

```bash
/opt/live.infinita/.venv/bin/python tools/run_failure_preference_008fa.py --output-dir /home/etbra/008fa-reproduction
python3 tools/validate_failure_preference_008fa.py docs/FAILURE_PREFERENCE_008FA
```

Os logs e JSON `regressions_on` e `regressions_off` registram os 50 nomes e resultados por modo. O exportador executa a mesma lista e rejeita erros de script.

## Aplicação e reversão

O instalador preparado não foi executado pelo agente. Ele exige checkout limpo, cria backup de código/configuração/web, executa exportação com testes, aplica a opção em drop-in separado, reinicia o renderer e exige status recente confirmando as quatro opções. Verifica o bridge e a versão pública. Falhas acionam restauração; banco, arquivos de experiências, animais e histórico de buscas não são apagados.

```bash
sudo bash /home/etbra/apply-failure-preference-008fa-root.sh
```

Para desligar a nova regra mantendo as experiências:

```bash
sudo bash /home/etbra/set-failure-preference-008fa-root.sh off
```

Para religar, use `on`. Após aplicação, conferir o status nativo recente e acompanhar decisões reais antes de atribuir benefício à live.
