# 008ED — Comparação física controlada: percepção, RAM e núcleo real

Executado em projeto Godot isolado, usando a cápsula e o motor de movimento atuais. Origem (-86, -80), destino (-68, -80), parede em x=-80 entre z=-180 e z=180 e abertura de quatro metros centrada em z=-30. Física, sondagem local, tentativa e erro, velocidade de 4 m/s e dt=0,1 s são os mesmos em todas as travessias. Não há BFS ou conhecimento da abertura fornecido ao navegador.

| Condição | Distância física XZ | Tempo simulado | Colisões | Chegou |
|---|---:|---:|---:|---|
| Percepção, RAM e recall desligados | 104,999 m | 31,5 s | 0 | Sim |
| Treinamento físico com RAM inicialmente vazia | 104,999 m | 31,5 s | 0 | Sim |
| RAM, três repetições separadas | 104,999 m cada | 31,5 s cada | 0 | Sim |
| Recall do núcleo real com RAM desligada | 104,999 m | 31,5 s | 0 | Sim |

As três repetições RAM tiveram 105 decisões de concordância cada. O recall real carregou 105 recomendações e teve 105 decisões de concordância. Nenhuma condição registrou escolha causal diferente da percepção. Neste cenário não houve redução de distância ou tempo. Ele confirma a utilização e concordância dos registros, não vantagem de aprendizagem.

O treinamento foi gerado por movimento real da cápsula e pelo recorder de ações existente. O percurso completo forneceu custos observados. O runner usa FastAPI TestClient, as rotas reais do SDK congelado `dfd87c995b50c49b45a9d5dd4c43cce456983d4f`, backend SQLite explícito e diretório temporário exclusivo. Armazena o percurso como uma observação estrutural, reabre o serviço e exige identidade e conteúdo integral iguais no GET de observações recentes antes de construir o snapshot de recall. Não há API simulada ou IDs inventados.

Na execução salva, a observação foi `structural-event:47bbbf436cabab834f4d2dbc57eaaab76a048d27`. Os 105 registros de passos pertencem a uma observação de percurso; não são 105 novas observações estruturais. O ID muda entre execuções pois a evidência inclui medidas de tempo de processamento. A recuperação alimenta o seletor existente; o SDK armazena/recupera os dados e a política da aplicação decide o movimento.

Limitação importante: o experimento armazena diretamente o percurso físico concluído, contornando intencionalmente a exigência de três reusos causais da promoção de produção. Isso permite testar o transporte real e o efeito do recall mesmo quando RAM só concorda com percepção. Não comprova promoção autônoma nem aprendizagem da live. O snapshot marca essa condição explicitamente. Os bônus já existentes são 1,5 para RAM e 2,0 para recall, portanto a diferença de política também deve ser considerada em outros cenários.

Tempo simulado significa ticks multiplicados por dt; não equivale à duração real registrada na live. `compute_wall_ms` mede apenas custo de execução do teste e não deve ser interpretado como melhora do caminhar. É um cenário determinístico e não uma amostra estatística de terrenos diversos.

Reprodução: `/opt/live.infinita/.venv/bin/python /home/etbra/live.infinita/tools/run_physical_memory_comparison_008ed.py --output-dir /home/etbra/008ed-physical-results`. Exige projeto isolado atual em /home/etbra/008bz-godot-test e o SDK congelado; sem núcleo real disponível, falha sem usar fallback sintético. Os logs cold e verified core e o JSON final estão salvos nesta pasta docs. As verificações físicas e de armazenamento/recuperação passaram.

Nenhuma física, serviço, história de produção ou release congelada foi modificada. Não precisa instalar nada. Próximo experimento: alterar uma passagem após o aprendizado, mantendo o restante fixo, para medir revalidação, recuperação e custo de decisões novas. Depois variar origens e destinos para avaliar a necessidade de generalização por contexto local.
