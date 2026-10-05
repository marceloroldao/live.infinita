# 008DB — Rotas lembradas são hipóteses verificáveis

A 008DA foi confirmada na live por 008DA_OK e 008DA_PUBLIC_OK, commit c5d3279. A janela nativa auditada durante a preparação da 008DB continha quatro chegadas e nenhuma colisão. Essa observação não é comparação controlada entre versões.

Um cenário que muda pode tornar inválidos um passo em andamento, uma rota calculada ou um passo recomendado pela RAM. Verificar apenas a existência do caminho antigo não basta: a geometria física atual precisa continuar tendo prioridade sobre a recomendação.

## Comportamento

- Um passo automático em andamento é revalidado pelo corredor físico até o ponto pendente. Se deixar de ser permitido, o navegador o abandona antes de insistir na execução.
- Uma rota calculada cujo próximo passo é rejeitado pela percepção é descartada. Nov pausa para planejar de novo, sem transformar essa percepção em uma colisão ou experiência de movimento fracassado.
- A contradição e uma falha realmente executada liberam imediatamente a próxima busca, ultrapassando o intervalo normal de cinco segundos ou doze metros.
- A exploração transitória da rota anterior é reiniciada: cobertura e direção antigas não podem impedir a busca de outra saída na geometria nova. O destino comprometido permanece.
- Recomendações temporárias contraditas são retiradas da RAM. Promoções históricas permanecem como evidência do passado e não recebem reforço por essa retirada.
- Somente um passo realmente concluído pode repor a experiência temporária. A promoção persistente continua exigindo três reusos causais distintos e bem-sucedidos.

A evidência de percepção contém route_revision com motivo, posição, ponto rejeitado e horário. A auditoria 008CZ passou a contar revisões observadas sem duplicar a mesma revisão durante vários quadros de planejamento, além dos passos concluídos com essa evidência. Esses campos não são contados como uso causal da memória.

Esta revisão não modifica o World State nem atribui a causa da mudança à Memoria.ia: detecta a mudança através das regras e colisões físicas atuais. Os mesmos limites de água, cápsula, altura por passo e janela de busca continuam valendo.

## Teste físico com cenário variável

A mesma geometria foi usada em três fases, alterando os corpos sólidos entre elas:

1. Passagem original aberta: chegada após 18,0 m, sem colisões.
2. Passagem original fechada durante um passo incompleto, nova abertura a seis metros do ponto antigo: chegada após 19,7493 m, sem colisões, uma revisão e uma nova busca.
3. Passagem original reaberta e a nova abertura fechada: chegada após 18,0523 m, sem colisões.

O teste deixou a posição atual livre ao mover os obstáculos. A RAM foi alimentada pelo sinal real de ações concluídas do gravador. A recomendação antiga foi removida após a contradição; o passo novo, realmente executado, substituiu a recomendação. O teste verificou também rejeição de uma rota previamente calculada, nova busca imediata, limite de RAM e preservação das promoções históricas.

Nenhuma tentativa bloqueada foi fabricada. A descoberta não gerou promoção automática. Os destinos e pontos iniciais das fases diferem, portanto essas distâncias não medem ganho causado pela memória.

Os 22 testes Godot da publicação passaram com saída zero e sem erros de script. Os 82 testes Python de navegação também passaram. A câmera estável e as colisões existentes foram preservadas.

## O que está demonstrado e o que falta

Esta etapa demonstra adaptação da navegação a uma geometria que mudou e atualização da experiência na RAM. Não prova generalização irrestrita da Memoria.ia nem ganho causado pelo seu armazenamento persistente.

A comparação seguinte deve executar a mesma situação nova com memória desativada e ativada, separar descoberta de reuso causal e verificar a promoção/recuperação após reinício. A observação da live também deve usar uma sessão nova após o rollout.

Um objetivo que se torne ocupado depois de já comprometido e mudanças que coloquem um objeto em cima do corpo requerem testes adicionais; este cenário alterou o corredor e manteve livre o objetivo e o corpo. A resolução física de destinos da 008DA continua ocorrendo ao comprometer um novo objetivo.

## Instalação

```bash
cd /home/etbra/live.infinita
git pull --ff-only
sudo bash deploy/apply-changing-routes-008db-root.sh
```

O instalador valida a exportação em cópia isolada, mantém backup e restaura a versão anterior em caso de erro. A conclusão é 008DB_OK em /home/etbra/008db-renderer-rollout.log. O envio ao GitHub não instala a versão na live.
