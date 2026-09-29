# MVP-018G — Diagnóstico real da recuperação do Nov

O relatório privado de MVP-018E, validado em 29/09/2026, confirmou 182
episódios, checkpoint estável e 181 correspondências históricas; cinco
lembranças retornadas tinham todos os seis endereços coincidentes.

Isso prova recuperação com proveniência, **não** diversidade de trajetórias
ou utilidade causal. Antes de conectar automaticamente ao Shadow Mode,
medir a distribuição de experiências e o custo real do cache.

## Comando único (usuário etbra, requer senha sudo)

```bash
cd ~/live.infinita && bash deploy/mvp018g-nov-memory-diagnostics.sh
```

Resultado esperado: `MVP018G_NOV_DIAGNOSTICS_OK`. O script salva apenas
contagens e tempos em `~/nov-memory-diagnostics.log` (0600). O usuário
`liveinfinita` lê o SQLite privado, WAL e checkpoint; somente código
público é copiado para uma pasta temporária em /tmp que é apagada ao final.
Episódios, chaves, IDs, assinaturas e payloads não são exportados.

O relatório inclui cardinalidade por endereço (necessidade, região, clima,
período, alvo, estratégia), número de combinações distintas e tamanho do
maior grupo idêntico. Também mede primeira carga e vinte consultas
reutilizadas, além de memória RSS máxima do processo.

O frame usado na comparação é **retrospectivo**, derivado da última
experiência confirmada e do ambiente do mundo; não afirma capturar a
posição/necessidade corrente de Nov. O resultado é inválido se a fonte
mudar entre as duas validações. Não executa propostas, World State,
reescrita do SQLite, central sync, BDR cutover ou restart.

## Gates de habilitação futura

1. Confirmar saída redigida e diversidade; não confundir seis endereços
   idênticos com aprendizagem ou inferência multimodal.
2. Avaliar latência e RSS com o histórico real; se exceder orçamento,
   otimizar o índice antes da ligação.
3. Criar provider opt-in com separação estrita do loop autoritativo e
   opção de reversão. O código atual permanece **desligado por padrão**.
4. Comparar baselines ex ante com/sem contexto antes de conceder
   qualquer influência decisória; sem LLM reingerida como evidência.

Referências: #88, PR #91, #92, #93.
