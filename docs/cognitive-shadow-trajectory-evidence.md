# Cognitive Shadow — trajetória e evidência de necessidade (v1)

O shadow é uma observação passiva do Single Writer. Não propõe, agenda, seleciona ou executa ações. O arquivo JSONL é separado do World State e o wrapper é fail-open: uma falha do observador não cancela o tick autoritativo.

## Semântica

- `best_candidate` é selecionado **após** o tick, comparando as alternativas do frame anterior com o estado observado. `selection_phase=posthoc` e `predictive_accuracy_evaluable=false` impedem interpretar `exact_match_rate` como precisão preditiva.
- `trajectory_observation` conserva posição/região da Nov antes/depois e níveis de necessidades quando disponíveis. Progresso em direção ao alvo usa a posição do alvo capturada antes do tick; se o alvo se moveu ou desapareceu, o progresso fica `null`, sem atribuição enganosa.
- `need_satisfaction_outcomes` usa apenas `npc_need_outcomes` retornados pelo runtime para o observador. Vincula por `plan_id` ao plano terminal do tick, registra valores medidos `before`, `after`, quantidade reportada, delta observado e eventual coincidência com o alvo selecionado post hoc. Ausência de dado permanece `null`; observação não é prova causal.
- Registros legados sem novos campos continuam válidos no resumidor. As novas contagens têm denominadores próprios e não são taxa de acerto.

## Validação e rollout

Rodar os testes com a virtualenv do projeto:

```bash
/opt/live.infinita/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

A mudança deve passar por PR/CI antes de deploy. O flag `LIVE_INFINITA_MEMORIA_V2_SHADOW` continua desabilitado por padrão no exemplo de configuração; o modo cognitivo continua sem `selection_authority` ou `direct_world_write`. O log existente é preservado em append-only. Não converter essas contagens em recompensa ou comando para a Nov sem novo contrato de previsão ex ante e gate separado.
