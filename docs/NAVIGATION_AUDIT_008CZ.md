# 008CZ — Medir a caminhada por sessão

A 008CY foi confirmada no renderizador nativo e no build público, commit b402e77. O serviço estava ativo e sem reinícios. Os episódios retidos continham sessões anteriores ao rollout; somá-los à sessão nova poderia atribuir resultados antigos à versão recém-instalada.

A auditoria agora permite `--latest-session` ou `--session ID`. A seleção usa o horário mais recente dos registros, não a ordem dos episódios no arquivo. A contagem mantém a deduplicação por sessão e decisão e separa também as rotas por sessão. A leitura não altera o arquivo de origem nem grava memória.

Por rota, o relatório acrescenta distância restante inicial e final, aproximação líquida ao destino, continuidade entre ações, aproximação por metro observado e repetições de passagens dirigidas com quantização de um metro. A proporção fica indefinida se houver lacuna entre ações ou mudança de objetivo. Um afastamento ou retorno pode ser necessário para encontrar uma passagem; estes indicadores não classificam automaticamente uma rota como inútil.

Os atalhos são contados somente nos passos concluídos. Atalho pela percepção não constitui aprendizado causal. As métricas causais de RAM e Memoria.ia continuam exigindo alternativa registrada diferente da escolha executada.

## Observação da live

Snapshot coletado após a instalação da 008CY, sessão a5a5db61db4903948bfad8d78fd9a838:

- 337 passos concluídos, 333,3038 m observados;
- 154 passos concluídos com atalho;
- nenhuma colisão e nenhuma chegada observada;
- 67 repetições de passagem dirigida;
- distância restante passou de 46,5064 m para 39,4150 m;
- nenhuma ação causal RAM ou Memoria.ia nesta janela.

Esta janela evidencia exploração com repetição, ainda sem chegada. Não demonstra que todo retorno foi desnecessário, que o destino é alcançável, nem ausência de aprendizado fora da janela. O próximo trabalho de navegação deve investigar os corredores próximos do objetivo e as condições que provocam retornos.

## Execução

Não requer instalação nem reinício do renderizador:

```bash
cd /home/etbra/live.infinita
bash deploy/audit-navigation-008cz.sh
```

O comando salva um relatório com horário no nome e imprime `008CZ_AUDIT_OK`. Para selecionar uma sessão específica, use diretamente `tools/audit_live_navigation_008cm.py --session ID --report CAMINHO`.

Oitenta testes Python de navegação passaram, incluindo oito novos casos: isolamento entre sessões, seleção por horário, sessão ausente, arquivo vazio, distância e revisitas, lacunas, afastamento necessário e contagem apenas de atalhos concluídos. Nenhum arquivo Godot foi alterado nesta etapa.
