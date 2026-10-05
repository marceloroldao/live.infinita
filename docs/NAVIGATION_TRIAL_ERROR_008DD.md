# 008DD — Motor experimental de tentativa e erro

O experimento produziu aprendizado incremental na RAM, persistência pela Memoria.ia e mudanças causais de decisões após reinício. O benefício foi misto: reduziu o percurso quando um passo aprendido ficou bloqueado, aumentou o percurso no U original e ficou neutro quando a passagem foi aberta.

## Motor e controles

O adaptador experimental herda os candidatos locais do navegador atual, mas desativa a busca observada de rotas em todos os modos. Não fornece um caminho correto nem um mapa de solução. O motor compara passos locais usando percepção física, visitas e resultados; o gravador entrega somente ações realmente concluídas à RAM. A percepção impede tentativas de atravessar obstáculos antes do movimento, por isso zero colisões não significa ausência de exploração.

A cada rodada de treinamento são limpos visitas, traço, falhas locais, rotas e recuperação. Somente a RAM, seu histórico de evidências e o contador de decisões permanecem. Foram seis caminhadas de treinamento: 32,67; 27,39; 28,05; 23,24; 19,94; 19,94 metros. Não houve melhoria monotônica. A RAM pode aprender durante cada caminhada, inclusive a primeira; essas distâncias descrevem aquisição, não substituem a avaliação controlada.

Cinco registros atingiram o critério de promoção: três decisões distintas e bem-sucedidas, com escolha diferente da alternativa sem RAM, chegada física ao passo escolhido e nenhuma colisão. O verificador relaciona cada prova à ação real. O processo de gravação recebeu cinco ACKs da API real do SDK da Memoria.ia em SQLite temporário; um novo processo reabriu o banco e recuperou exatamente os cinco IDs e destinos.

A avaliação usa navegador e estado transitório novos a cada execução e não aprende passos novos. Os três modos recebem respectivamente nenhum conhecimento, os cinco passos promovidos reconstruídos na RAM, ou os mesmos cinco recuperados da API com RAM desativada. A RAM final do treinamento contém 27 recomendações; o comparativo usa somente as cinco promovidas para igualar o conhecimento disponível. Recomendações continuam sujeitas à física atual.

Não foi alterado o núcleo da Memoria.ia. Neste teste ele persiste e recupera experiências; a seleção local e o critério de aprendizado pertencem ao navegador. A busca global ficou comprovadamente desativada: zero construções de rota em treinamento e avaliação.

## Resultado controlado

Duas repetições por cenário e modo, total de 18 avaliações. Início, objetivo, cápsula, geometria, velocidade de 4 m/s e passo de simulação de 0,1 s iguais.

| Cenário | Sem experiências | RAM: cinco passos | Memoria.ia após reinício |
|---|---:|---:|---:|
| U original | 40,58 m | 42,13 m | 42,13 m |
| Parede frontal removida | 6,00 m | 6,00 m | 6,00 m |
| Passo aprendido bloqueado por novo obstáculo | 58,59 m | 30,80 m | 30,80 m |

Todos chegaram sem colisões. As duas repetições reproduziram distância, tempo de movimento, revisitas e quantidade de escolhas causais. No terceiro cenário, o ganho de percurso foi de 47,44%, o tempo simulado de movimento caiu de 17,6 para 9,2 segundos e as revisitas de 15 para 4. No U original houve regressão de 3,84%.

Em cada repetição, a RAM e a Memoria.ia mudaram cinco escolhas concluídas no U original e três no cenário alterado. No caminho aberto não mudaram nenhuma. A confirmação exige diferença superior a 5 cm entre a escolha executada e a alternativa sem a fonte de memória. Portanto o efeito não é apenas concordância com a percepção.

O teste comprova recuperação persistente e benefício causal em um cenário alterado específico. Também mostra que repetir um passo bem-sucedido não garante a melhor rota. Não comprova generalização universal, desempenho na live ou um novo algoritmo de aprendizado dentro do núcleo da Memoria.ia. Os tempos são simulados, não latência do servidor.

## Evidência e reprodução

O resumo está em NAVIGATION_TRIAL_ERROR_RESULT_008DD.json. NAVIGATION_TRIAL_ERROR_EVIDENCE_008DD.json.gz contém as ações completas, recibos, recuperação e provas de promoção; o resumo guarda o SHA-256 do relatório descomprimido.

Os 94 testes Python de navegação passaram. Sete verificações deste comparador rejeitam falsa causalidade, tentativas fracassadas contadas como sucesso, IDs sem recibo, conhecimento desigual, braços ausentes e busca global ligada; preservam também resultados sem chegada.

Execute no servidor, sem instalação:

```bash
cd /home/etbra/live.infinita
bash deploy/run-navigation-trial-error-008dd.sh
```

O roteiro usa o projeto isolado já preparado e um banco temporário exclusivo. A live e sua memória de produção permanecem na versão instalada.

O próximo avanço é avaliar o resultado de uma sequência completa, reduzindo o peso de experiências que prolongam o caminho. Essa alteração deve passar novamente pelos mesmos controles, incluindo a regressão no cenário original, antes de entrar na live.
