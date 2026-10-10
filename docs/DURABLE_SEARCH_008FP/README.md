# 008FP — busca com registro durável e orçamento compartilhado

A busca de 008FO agora usa `nov_contact_search_journal.gd`. O início é gravado antes de devolver a intenção de movimento. O arquivo usa envelope com checksum, gravação temporária, troca atômica e permissões 0600. Falha na gravação ou corrupção impede novo início.

O registro é de execução, separado da Memoria.ia. Conserva o identificador da aproximação anterior, animal, mundo, instante inicial e instante da observação usada como semente. Uma busca só pode iniciar uma vez por aproximação. Há limite de quatro inícios por mundo e período lógico de cinco minutos; interrupções contam. O histórico admite até 64 inícios e 16 mundos, sem remover identificadores para permitir repetição. Ao atingir a capacidade, novos inícios são bloqueados; rotação de histórico ainda não foi implementada.

## Reinício

Uma busca pendente não é retomada automaticamente com uma posição antiga. Na recarga, ela é arquivada como `renderer_restart`, com horário final, distância, observação de reencontro e posição de reencontro desconhecidos. Continua consumindo o orçamento. Uma busca concluída preserva seu resultado medido e não volta a iniciar para a mesma aproximação.

O reencontro continua distinto de uma aproximação concluída ou captura. Todos os registros de busca têm `learning_eligible=false`, `approach_confirmed=false`, `capture=false` e `absence_claim=false`.

## Orçamento compartilhado

O consumidor Python de 008FK aceita agora o parâmetro opcional `contact_search_journal`. Ao reservar exploração, ele consulta os inícios de busca do mesmo período e bloqueia outra execução quando existe busca pendente. Uma interrupção não devolve a tentativa consumida.

Do outro lado, `search.configure(journal_path, shared_guard_path)` faz o consumidor Godot consultar as reservas de exploração antes de iniciar a busca. Uma exploração pendente bloqueia a busca; explorações concluídas ou interrompidas do mesmo período contam junto com ela. Assim, três buscas mais uma exploração consomem os quatro inícios; quatro explorações impedem uma busca adicional.

A conexão exige que o consumidor forneça ambos os caminhos: a chamada Python deve receber o registro de buscas, e a configuração Godot deve receber o guard de exploração. Sem esses parâmetros opcionais, cada componente conserva apenas seu próprio orçamento. A integração foi validada em testes e ainda não está habilitada na live.

## Validação física

| Caso | Trajetos com busca | Recarga em outro processo Godot | Resultado |
|---|---:|---:|---|
| Concluído | 2 | 2 | Reencontro medido preservado, sem pendência |
| Interrompido após cinco passos de busca | 2 | 2 | `renderer_restart`, distância e instante final desconhecidos |

Cada execução tem um controle que termina ao perder contato: oito trajetos físicos no total. As aproximações iniciais dos dois braços conservam o mesmo resultado e distância. Nos casos interrompidos, o movimento parcial existe nos diagnósticos físicos, mas não é promovido a distância final medida do registro durável.

Quatro fatos reais de perda de contato da aproximação inicial foram confirmados e recuperados em quatro reaberturas do núcleo SQLite, com remoção do cache e sem POST na recuperação. Nenhum registro de busca foi incorporado como fato de aprendizagem.

A auditoria dos arquivos selados confirma um início consumido antes e depois de cada recarga. A pendência desaparece após arquivar a interrupção; o contador não diminui. Os arquivos antes/depois e os logs dos processos separados estão em `evidence/`.

## Testes

- 52 testes Python, incluindo seis novos contratos de orçamento compartilhado.
- O teste de interoperabilidade usa o guard Python real com quatro reservas encerradas e comprova que o consumidor Godot recusa outra busca.
- 21 contratos Godot do registro: pendência, recarga, repetição, vínculos, orçamento, relógio, corrupção e falha de gravação.
- 18 contratos Godot da busca continuam aprovados.
- Auditoria dos quatro registros físicos antes/depois da recarga em `shared-budget-audit.json`.

Os contratos sintéticos de orçamento não são experiências físicas nem fatos do núcleo. Os ensaios físicos continuam planos, diurnos e prescritos, sem ecologia, captura ou câmera completa renderizada.

## Escopo

Esta implementação atende um ator serial e armazenamento local. A trava Python protege seu próprio arquivo; não há transação atômica entre os dois arquivos ou coordenação distribuída. Consumidores concorrentes de exploração e busca exigiriam um único serviço de reservas antes de habilitar esse uso.

A live permanece em coleta (`decision_use=false`), conforme `live-health.json`. Nenhum serviço foi modificado ou reiniciado. O núcleo armazena e recupera fatos estruturais; a busca e o controle de execução pertencem aos consumidores.

Reprodução sem sudo:

```bash
cd /home/etbra/live.infinita
/opt/live.infinita/.venv/bin/python tools/run_durable_search_008fp.py --output-dir /home/etbra/008fp-repeat
```
