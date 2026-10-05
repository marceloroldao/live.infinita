# 008DH — Saída de lago cognitivo e status durante bloqueio

Corrige a situação observada após instalar a 008DG: Nov começou dentro de uma área classificada como cognitive_lake, todos os passos foram rejeitados e o arquivo de status permaneceu com dados do processo anterior. O renderizador estava ativo, mas a caminhada não progredia.

## Regra física de saída

A classificação do terreno cognitivo passa a fornecer escape_depth_m: soma das distâncias horizontais restantes até as bordas dos lagos que cobrem o ponto. Não é profundidade vertical da água nem um caminho global calculado.

Se o corpo já está numa área cognitive_lake e há informação física válida, os passos na água só são admitidos quando esse indicador diminui em todas as amostras do segmento. Entrar num lago a partir de terra firme, ir mais para dentro, cruzar o rio sem ponte e atravessar limites do mapa continuam proibidos.

O limite de altura, a cápsula, a varredura de colisão e o teste de ocupação final são mantidos. A saída não teleporta o corpo, não desativa obstáculos e não muda o destino. Quando alcança terra firme, volta à regra normal de caminhada. Não foram acrescentadas animações de natação nem navegação aquática geral.

A seleção entre os passos admissíveis continua sendo feita pelo motor local, com tentativa e erro, visitas, RAM e recuperação da Memoria.ia. A permissão de saída é uma regra física de recuperação; não é apresentada como uma descoberta feita pela Memoria.ia. Somente passos realmente concluídos alimentam a experiência, pelos critérios já existentes.

Não há saída autorizada se a informação de margem falta ou é inválida. Obstáculos, terreno demasiado íngreme ou geometrias complexas ainda podem impedir uma saída segura; nesses casos o motor conserva as restrições e o status informa que procura passagem.

## Status vivo

O arquivo de status passa a receber atualização também nos quadros em que a percepção rejeita todos os candidatos. Usa o mesmo limite de gravação de dois segundos, evitando que a ausência de movimento seja confundida com ausência de dados do servidor.

Os estados publicados são walking, water_egress, no_passage e idle. O exportador valida os estados, mantém os contadores observados e limita o tamanho da razão. O painel usa “Saindo do lago” ou “Procurando passagem” quando apropriado. Uma percepção sem passagem não conta como chegada, passo concluído ou colisão executada.

## Teste físico

O teste cria um lago de raio 5 m durante um passo real de Nov. Uma parede já está na direção do objetivo. O motor completa a caminhada após a mudança, com cerca de 9,0 m percorridos após a formação do lago, 9,4 m no total, dez passos concluídos, zero colisões e zero buscas globais de rota.

Verifica também entrada da terra para a água, movimento para dentro do lago, travessia do rio, parede física, altura excessiva, informação de margem ausente e atualização de status enquanto não há passagem. Cada passo realmente executado na água reduziu o indicador de distância à margem.

106 testes Python passaram, incluindo o transporte dos estados de saída e bloqueio, preservação de contadores e rejeição de estado inválido. A suíte Godot inclui os testes anteriores e o novo ensaio físico. O resumo de resultados e hashes fica em WATER_EGRESS_RESULT_008DH.json.

Os resultados acima são de uma geometria sintética. A saída da posição observada na live só poderá ser confirmada depois da instalação desta versão.

## Instalação

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-water-egress-008dh-root.sh
```

O instalador inclui o terreno cognitivo, as regras de travessabilidade, o módulo de movimento, o painel, as jornadas e o exportador de status. Recompila a página, reinicia o renderizador e verifica os flags publicados. Mantém backup e restauração em caso de falha.

Registro: /home/etbra/008dh-renderer-rollout.log. Confirmação: 008DH_OK. Nenhuma instalação de administração foi executada durante a preparação.
