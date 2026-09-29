# MVP-018H — Comparação de recuperação por trajetórias observadas

## Evidência que motivou o experimento

O diagnóstico privado do MVP-018G retornou 192 episódios; somente 6 combinações
distintas dos seis endereços, com 81 observações na maior combinação.
Estratégia e clima tiveram 1 valor distinto cada. O baseline do MVP-018E
selecionou cinco lembranças com coincidência de 6/6 endereços. No ensaio
retrospectivo MVP-018G, a mediana de cache foi 1,968 ms (20 consultas), com
pico de 64,215 ms; primeira reconstrução 127,26 ms. Estes valores não são
previsões sobre carga futura nem avaliação da ação autônoma do Nov.

## Contrato do comparador (desligado por padrão)

A nova camada `nov_trajectory_recall_shadow.py` opera **somente sobre o índice
privado já verificado pelo EvidenceCore V2**. Uma trajetória observada mantém
duas partes:

- vetor exato de endereços confirmados: necessidade, região, período, clima,
  alvo e estratégia;
- vetor tipado de resultado testemunhado: satisfação, risco observado, ticks
  transcorridos, preempções e replanejamentos. Nulos permanecem nulos.

Nenhuma dessas grandezas recebe rótulo inventado de sucesso, recompensa,
causalidade ou significado semântico. Uma diferença numérica real é uma
diferença observada, não uma prova de comportamento melhor ou pior.

O comparador usa o mesmo conjunto candidato, a mesma interseção de endereços,
o mesmo episódio-semente excluído e a mesma proveniência do baseline.
O baseline devolve as observações mais recentes entre as coincidências.
A alternativa experimental seleciona primeiro um representante por perfil
observado distinto, respeitando a prioridade original por coincidência; se
faltarem representantes, preenche com as observações restantes por recência.
O relatório apresenta separadamente coincidências completas/parciais: mais
diversidade pode significar menor coincidência, nunca uma vitória automática.

A distribuição temporal conta transições **dirigidas** entre vetores de
endereços consecutivos e repetições de vetor. É descrição de sequência,
não previsão de ação ou inferência causal.

## Segurança

A interface operacional permanece a mesma do MVP-018G:

```bash
cd ~/live.infinita && bash deploy/mvp018g-nov-memory-diagnostics.sh
```

O script proprietário monta somente código Python público em /tmp. O usuário
`liveinfinita` lê o snapshot privado, o checkpoint e os dados observados.
A saída `~/nov-memory-diagnostics.log` (0600) expõe **apenas contagens**,
sem valores de resultado, endereços, IDs de evidência, hashes ou payload.
A assinatura de origem é novamente conferida antes e depois da medição;
a consulta não escreve na memória operacional nem no mundo.

O comparador **não está conectado ao `CognitiveShadowRecorder` de produção**:
não substitui a recuperação atual, não altera política de ações, não cria
associações estruturais persistentes, não migra para BDR e não sincroniza
com o servidor central. A ligação só será discutida depois de medir se
representantes distintos revelam trajetórias úteis e se o custo/cadência
não interfere na simulação.

## Gates

1. Testes de relevância, repetição, outcome nulo, privacidade e ordem temporal.
2. Teste fim-a-fim usando a Memoria.ia V2 exata e checkpoint de ensaio.
3. Comparação real redigida de baseline e alternativa: perfis candidatos e
   recuperados, coincidências completas/parciais e transições.
4. Só então considerar inferência sobre relações endógenas no repositório
   apropriado, mantendo toda evidência ligada à trajetória original.
