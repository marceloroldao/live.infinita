# MVP-018M — diagnóstico da cauda de latência após gate bloqueado

O canary real de 29/09/2026 concluiu 60 ciclos e contabilizou 91 chamadas
ao monitor, com 52 leituras prontas (57,14%), 39 abstenções, 32 envios,
46 avanços e zero regressões de tick. Pico de RSS: 53.856 KiB.
A mediana do monitor foi 1,469 ms, mas o maior tempo observado foi
760,384 ms; portanto, o gate de 250 ms bloqueou **apenas**
`resource_budget`. O banco e a origem da cauda não foram inspecionados:
não atribuir o pico a SQLite, GC, disco, lock, servidor ou escalonador.

## Instrumentação corretiva

Agora todo `ContinuousOwnerMonitor.step()` mede separadamente, por relógio
de parede, o tempo em três trechos: `sampler` (frame atual sob lock de
leitura não bloqueante), `peek` (contexto preparado em RAM) e `submit`
(fila de capacidade um para a preparação fora do tick). A medição usa
rótulos estáticos e publica só máximos de duração, sem valores de frames,
IDs, endereços, evidências, hashes ou exceções.

O coletor mede **todas** as chamadas de `step`, inclusive chamadas
adicionais após o `wait_ready` do canary. Antes, a distribuição de
latência cobria somente a primeira chamada de cada ciclo. A memória
estatística é limitada aos últimos 256 tempos de `step`, em vez de
crescer indefinidamente para um processo permanente. O máximo observado,
a contagem de etapas acima de 250 ms/500 ms e o desdobramento da pior
etapa acumulam durante toda a execução. No ensaio de 60 ciclos, todos os
tempos cabem na janela.

`worst_step_phase_ms` registra `sampler`, `peek`, `submit` e tempo
`unattributed` (diferença entre total e os três trechos) **da mesma
etapa mais lenta**. `phase_max_ms` registra máximos de cada trecho,
possivelmente em etapas diferentes. Uma demora de relógio de parede
também pode refletir preempção pelo SO dentro de um trecho medido;
o campo identifica a localização temporal, não a causa raiz.

O gate existente continua exigindo no máximo **250 ms** por etapa,
sem aumentar limites para conseguir aprovação. Rejeita contagens ou
estrutura impossíveis e mostra os quatro trechos numéricos do pior
caso quando bloqueia. A origem histórica e a ausência de autoridade
de seleção, escrita no mundo, sync central e BDR permanecem inalteradas.

## Execução repetida, finita, sem serviço permanente

```bash
cd ~/live.infinita && git pull --ff-only && bash deploy/mvp018m-nov-extended-canary.sh
```

O relatório 0600 `~/nov-memory-extended-canary.log` será refeito;
o comando dura cerca de dois minutos e continua exclusivo do usuário
proprietário da memória. A unidade systemd de preparação não é
instalada, iniciada ou habilitada. Quando aparecer o marcador final,
inspecionar especificamente `max_step_ms`, `slow_step_gt_250_count`,
`slow_step_gt_500_count`, `phase_max_ms`,
`worst_step_phase_ms`, `ready_fraction`, tick e RSS. Mesmo um
novo gate aprovado será evidência de um **ensaio finito**, não de
funcionamento contínuo ou qualidade das decisões do Nov.

Para comparar cargas de maneira controlada, preservar o mesmo ciclo,
intervalo e threshold. Não estimar causa de um único pico sem múltiplas
janelas observacionais; repetir se a suspeita for escalonamento ou
concorrência de I/O. Somente depois disso discutir serviço permanente
e autenticação forte entre processos de mesma UID.
