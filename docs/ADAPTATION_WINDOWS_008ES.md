# 008ES — custo após exploração na sessão nativa

Análise somente de leitura da versão 008ER em produção (build 5e3ef78).
Captura desde 2026-10-08 06:54:07 UTC até 07:25:49 UTC: 562 eventos,
281 contatos, sem linhas inválidas, conflitos ou resultados sem decisão.

A memória recuperada mudou o lado inicial em oito contatos com saída física
concluída. A RAM mudou o lado em outros três. Isso demonstra influência na
decisão e execução local bem-sucedida, mas não demonstra vantagem causal.

## Exploração e decisões seguintes

A análise agrupa mundo, assinatura sensorial exata e identidade de início da
janela de aumento de custo. Ordena exclusivamente pelo horário físico de
conclusão; a ordem do vetor da captura não é considerada cronológica.
Os eventos não fornecem horário de início da decisão; a ordem de conclusões
não comprova que a decisão começou após a exploração ou usou seus resultados.
Onze janelas foram observadas; duas contêm exploração concluída e, em horário
posterior, conclusão de uma preferência aprendida aplicada:

| Assinatura local | Explorações iniciais concluídas | Decisões aprendidas posteriores | Distância média inicial | Média posterior |
| --- | ---: | ---: | ---: | ---: |
| 255:254, início nesta sessão | 3 | 7 RAM | 3,994 m | 3,857 m |
| 126:126, início herdado | 2 | 1 recuperada | 10,000 m | 16,587 m |

A primeira diferença é pequena e a segunda tem custo maior. Assinaturas iguais
não garantem obstáculos, relevo ou geometria iguais. Essas médias incluem
somente contatos concluídos e não contabilizam custo desconhecido dos contatos
interrompidos. Não houve redução consistente demonstrada, nem estimativa
válida de economia líquida incluindo aquisição.

Outra janela herdada, de assinatura 255:254, contém sete das oito decisões
recuperadas que mudaram o lado e concluíram. Não há exploração concluída
anterior nessa mesma janela dentro desta captura; essas decisões não são
atribuídas às novas explorações da sessão.

## Contatos sem conclusão

Das 200 explorações: 42 concluíram, duas tiveram falha física e 156 foram
excluídas antes de uma saída confirmada. Destas, 148 registraram
observed_side_end e oito new_contact_before_executed_exit.
Exclusão não é sucesso nem falha física; não deve receber recompensa ou
penalidade inventada. Os números estão preservados na análise.

Próxima investigação: reproduzir os encerramentos observed_side_end com
movimento físico e verificar continuidade do contato e conclusão real. Só
depois decidir se há correção do ciclo de contato ou necessidade de distinguir
melhor contextos sensoriais. Não converter exclusões em aprendizado por regra.

## Uso e validação

Na VM, executar sem root:
`bash /home/etbra/measure-adaptation-windows-008es.sh`.
Faz uma captura limitada e gera JSONs em /home/etbra; não instala agendamento.
A ferramenta também analisa uma captura arquivada com
`python3 tools/analyze_adaptation_windows_008es.py --input captura.json --output analise.json`.

Vinte testes de contrato passaram: dez do observador anterior e dez novos,
incluindo ordem reversa, timestamps inválidos, empates, janelas distintas,
preferência não aplicada, classificações adulteradas e exclusões.
Esses testes são sintéticos e nunca entram na memória da live.

Evidência integral em ADAPTATION_WINDOWS_008ES/: capture.json, events.log,
analysis.json, tests.txt e health.json. Nenhuma mudança no movimento, banco de
memória, painel ou serviço de produção foi aplicada nesta etapa.
