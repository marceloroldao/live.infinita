# 008EE — Passagem alterada após treinamento físico

Treinamento real da cápsula no mesmo cenário 008ED: início (-86,-80), destino (-68,-80), parede em x=-80 entre z=-180 e z=180, abertura de quatro metros centrada em z=-30. Depois o teste fecha essa abertura e abre outra em z=-130. Todas as condições comparadas recebem exatamente a mesma geometria alterada e começam na origem. O navegador não recebe a posição da abertura. Tentativa e erro, percepção de três metros, cápsula, velocidade 4 m/s e dt=0,1 s permanecem iguais. Não há busca global/BFS.

| Condição | Distância XZ | Tempo simulado | Colisões | Chegou |
|---|---:|---:|---:|---|
| Treinamento no mapa antigo | 104,999 m | 31,5 s | 0 | Sim |
| Percepção no mapa alterado | 527,952 m | 158,4 s | 0 | Sim |
| RAM antiga, repetição independente 1 | 527,952 m | 158,4 s | 0 | Sim |
| RAM antiga, repetição independente 2 | 527,952 m | 158,4 s | 0 | Sim |
| Recall antigo do núcleo real | 527,952 m | 158,4 s | 0 | Sim |

Todas as condições do mapa alterado atravessaram em z=180,707, pelo fim livre da parede. Nenhuma atravessou a nova abertura em z=-130. Isso é chegada física segura com um desvio longo, não demonstração de descoberta da nova abertura. A parede fechada não foi atravessada.

A RAM teve 52 decisões de concordância por repetição. O recall carregou 105 recomendações antigas verificadas e teve 53 decisões de concordância. Nenhuma condição mudou escolha de forma causal pela memória. Os contadores de invalidação de candidato RAM e rejeição direta de endpoint recuperado foram zero; não inventamos uma contradição física registrada. A percepção e o contorno desviaram antes de executar a antiga travessia.

As repetições RAM são independentes: cada uma recebe cópia da RAM do treinamento antigo, sem os resultados da primeira repetição no mapa alterado. O recall usa RAM desligada e recomendações do percurso antigo armazenadas/reabertas/recuperadas pelo SDK real congelado, SQLite, sem fallback. O evento salvo nesta execução é `structural-event:c4bc567e7071e6e4a2f0241d19963cc8c9b99e48`. Há uma observação de percurso contendo 105 passos, não 105 eventos novos.

O armazenamento direto do percurso concluído é restrito ao experimento de transporte: contorna explicitamente o critério de promoção causal da produção. Portanto não comprova promoção autônoma, aprendizagem generalizada ou vantagem da live. O SDK recupera evidência; a aplicação calcula as escolhas. Os bônus existentes de RAM (1,5) e recall (2,0) permanecem inalterados.

Verificações: geometria física, cruzamento aberto, ausência de colisões/BFS, conclusão válida do treinamento e igualdade integral do evento armazenado/recuperado. O teste original 008ED foi repetido após a refatoração do benchmark compartilhado, mantendo zero falhas e diferenças zero entre percepção e recall. O benchmark agora também conserva o resultado de não chegada, caso ocorra, e não calcula diferença de custo como melhoria quando uma condição não chega.

Reprodução: `/opt/live.infinita/.venv/bin/python /home/etbra/live.infinita/tools/run_changed_passage_memory_008ee.py --output-dir /home/etbra/008ee-changed-results`. Usa o projeto Godot isolado e o núcleo congelado já descritos na 008ED. Resultados, logs e verificação do cenário original estão junto desta documentação.

Escopo: um caso determinístico; tempos são ticks multiplicados por dt, não segundos de transmissão. O teste ocorre fora da live e não altera serviços, histórico de produção ou release congelada. Não exige instalador.

Próxima evolução a testar: explorar outra direção após um desvio prolongado e organizar evidências por contexto local para reutilizá-las quando destino ou passagem mudam. Qualquer política nova deve usar somente percepção/experiência observadas, revalidar cada passo pela física e passar pela comparação com o mesmo mapa, incluindo limites e não chegadas. Não fornecer coordenadas da nova abertura nem ajustar pesos para fabricar vantagem.
