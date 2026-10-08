# 008EU — verificação da aplicação na live

Rollout concluído pelo usuário: 008eu-20261008T181031Z. Promoção
008ca-20261008T181328Z; build público eb4b801. Renderer iniciado às
18:12:47 UTC (15:12:47 em São Paulo), ativo com NRestarts=0 na verificação.

A regra de direção da saída, a continuidade 008ET e a adaptação por custo 008ER
estão ligadas no estado nativo. Os arquivos de contorno e coletor são idênticos
aos do repositório. Não foram encontrados erros de script/parse/loading desde
o início dessa sessão. A ponte de padrões terminou com sucesso e seu timer
continua ativo. Os recibos confirmam gravação e recuperação; o cache recuperado
contém 512 registros. Essa janela não representa todo o histórico nem deve ser
somada à janela local como se fossem fatos distintos.

## Captura de decisões e resultados

De 18:12:47 até 18:21:42 UTC: 113 eventos, 57 contatos, sem linhas inválidas,
contatos inválidos, conflitos ou resultados sem decisão.

- Nove explorações concluídas.
- Quatorze escolhas da memória recuperada mudaram o lado e concluíram a saída.
- Vinte escolhas recuperadas sem mudança de lado concluíram.
- Três escolhas da RAM sem mudança de lado concluíram.
- Dez contatos por percepção concluíram.
- Um contato recuperado sem mudança de lado ficou sem resultado nesta captura.
- Nenhuma exclusão ou falha física foi registrada nessa janela.

Resultado ausente não é falha nem prova de contato ainda pendente no snapshot
posterior. As contagens são da captura fixa, não de um monitor contínuo.
Mudança de escolha com conclusão demonstra influência da evidência recuperada;
não comprova vantagem causal ou menor custo sem comparação física equivalente.

## Ações físicas recentes

O snapshot limitado de episódios foi filtrado pelo horário de início do renderer.
Nas 24 ações executadas sem colisão que carregavam proposta de saída, não houve
recuo na normal medida. O menor progresso foi aproximadamente 0,799 m.
Isso confirma a direção física observada nesse subconjunto; não é garantia de
que toda situação futura terá conclusão, nem de redução líquida de custo.
A janela dos episódios é diferente da janela fixa de decisões/resultados.

Evidência integral em EXIT_PRODUCTION_008EU/: checks.json, status.json,
rollout.log, events.log, outcomes.json, windows.json, native-episodes.json.gz
e exit-projections.json. A coleta foi somente de leitura; nenhuma nova regra
foi aplicada durante a verificação.

Próxima evolução: comparar custos em situações fisicamente equivalentes usando
experiência recuperada e percepção, contabilizando aquisição, falhas e contatos
sem conclusão. A correção da saída está confirmada, mas melhoria aprendida na
live ainda exige esse controle.
