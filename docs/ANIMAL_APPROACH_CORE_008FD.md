# 008FD — Aproximações observadas no núcleo Memoria.ia

A ponte lê o histórico privado produzido pelo renderer 008FC, confere seu checksum SHA-256 e valida cada resultado. Envia somente resultados não censurados com movimento efetivamente medido: aproximação confirmada, perda de contato, falta de progresso ou orçamento esgotado. Intenções pendentes, reinícios, pausas e demais interrupções permanecem no histórico local e não entram nesta trilha do núcleo.

O serviço não cria captura, observações visuais, estratégias ou alterações no mundo. A navegação e o renderer continuam na versão 008FC. O histórico local continua com `core_ingestion=false` porque seu produtor não chama o núcleo; a confirmação da ponte independente está em `/godot/wildlife/approach-core.json`.

## Identidade e recuperação
Cada evento estrutural tem identidade derivada do conteúdo normalizado. Tempos lógicos e revisão inteiros recebidos como float de Godot são normalizados; distâncias preservam os valores medidos. A proveniência conserva mundo, animal, resultado, medidas e marcadores de fato. A resposta precisa confirmar armazenamento SQLite durável com identidade correspondente. Cada confirmação é registrada imediatamente no checkpoint; uma falha parcial retoma sem duplicar eventos.

A recuperação usa envelopes retornados pela API estrutural, valida evento, proveniência e identidade completos, e conserva até 512 resultados recuperados. Receber ACK não conta como recuperação. O estado público distingue `confirmed_total`, `recovered_this_poll` e `cached_recovered`. O cache guarda fatos recuperados anteriormente; uma janela recente da API não prova que todos eles voltaram neste poll. Não se atribui a esta recuperação qualquer uso na decisão: `decision_use=false` e `learned_hunting=false`.

Limites: até quatro ingestões por execução; fonte até 512 resultados; janela recente da API limitada a 64 itens, com tolerância delimitada a concorrência. Uma fonte modificada com o mesmo identificador, checksum inválido, sucesso sem proximidade, previsões ou respostas incoerentes fazem a execução falhar. O estado público deixa de ser atualizado em falha e deve ser avaliado por sua data, não como saúde permanente.

## Evidência
Cinco resultados reais, publicados pelo renderer da live, foram preservados sem alterar medidas em `ANIMAL_APPROACH_CORE_008FD/production_public_outcomes.json`. Para testar a ponte sem acessar nem escrever o núcleo de produção, esses resultados receberam apenas um envelope de serialização em um diretório temporário.

O SDK congelado `dfd87c995b50c49b45a9d5dd4c43cce456983d4f` abriu SQLite com `allow_fallback=false`. Os cinco foram armazenados. O serviço foi reaberto e o arquivo de recall removido; os mesmos cinco resultados voltaram pela API, sem nova ingestão. Evidência: `CORE_VALIDATION_008FD.json` e `cold_recovered_outcomes.json`. Isto demonstra armazenamento e recuperação duráveis; ainda não demonstra melhoria de decisão na caça.

Validação concluída: 46 testes Python passaram, incluindo 12 contratos da ponte, seis do instalador, regressões do bridge de padrões de navegação e de memória de encontros. O fixture de encontros foi renovado por um teste real do sensor Godot, sem alterar o teste antigo nem sua janela de frescor. Sintaxe shell e unidades systemd verificadas; avisos de unidades xfs do sistema são externos às novas unidades. Nenhum código de renderer mudou nesta etapa.

## Operação
Novos arquivos: `nov_animal_approach_sync.py`, `live-infinita-animal-approach.service` e `live-infinita-animal-approach.timer`.
Timer: 30 segundos após terminar a execução anterior, atraso aleatório até três segundos. Utiliza somente API local, usuário liveinfinita, ambiente de autenticação já existente e diretórios delimitados. Não imprime credenciais.

Instalação pelo usuário:
`sudo bash /home/etbra/apply-animal-approach-core-008fd-root.sh`

O instalador exige renderer saudável e histórico 008FC presente, faz backup de código e unidades, ativa a ponte, verifica publicação recente e recuperação quando há resultados elegíveis. Rollback restaura código/unidades e preserva dados do núcleo e checkpoints. Não reinicia o renderer nem altera o build público da cena. Aplicação confirmada na produção: rollout d8d23a5 concluído em 09/10/2026 às 22:04 de São Paulo. Timer ativo, execução com resultado success e módulo instalado igual ao repositório. Seis resultados elegíveis confirmados no núcleo e seis recuperados durante o rollout. Verificação posterior conserva seis no cache de fatos recuperados, sem duplicação; recovered_this_poll pode ser zero quando saem da janela recente. Sem erros da ponte desde a instalação. Recuperação fria da produção não foi forçada; permanece comprovada no núcleo isolado.

Próxima etapa: comparar escolhas usando os fatos recuperados com a mesma situação e percepção, incluindo aproximações malsucedidas e alteração do comportamento dos animais. Somente depois desse teste atribuir melhoria à memória e evoluir para captura.
