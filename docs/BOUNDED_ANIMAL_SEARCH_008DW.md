# 008DW — busca física limitada a partir de encontros lembrados

Conecta as regiões da 008DU a uma intenção de busca no renderer nativo. O modelo continua sendo recorrência espacial da aplicação sobre encontros realmente armazenados e recuperados pela Memoria.ia; o núcleo congelado não é alterado.

## Início, limites e comparação
Uma tentativa só pode começar quando:
- a caminhada normal terminou;
- há previsão válida, com pelo menos 20 segundos restantes, três IDs distintos de encontros recuperados e a mesma identidade de mundo e sessão;
- o animal não está no avistamento físico atual;
- o alvo está a até 40 m de Nov, dentro do raio de residência local de obstáculos;
- o resolvedor físico aceita o destino, sem ajustar mais de 4 m;
- o intervalo desde a última tentativa é de pelo menos cinco minutos lógicos;
- ainda não ocorreram quatro tentativas no ciclo atual de 60 minutos lógicos.

As tentativas alternam entre `memory` (centro da região por recorrência) e `last_seen` (último local observado, igualmente recuperado). A ordem persiste após reinício. Este é um experimento por alternância, não um teste randomizado nem uma demonstração causal de superioridade.

Cada busca tem no máximo 45 segundos lógicos e deve terminar antes do prazo da previsão. Há ainda um limite de 60 segundos de tempo monotônico se o relógio lógico parar. Quinze segundos sem melhorar a aproximação encerram a tentativa. Na chegada a até 2 m do alvo, Nov permanece no ponto realmente alcançado e gira o corpo durante até oito segundos para observar. A câmera mantém sua orientação de acompanhamento.

## Física e experiência
A intenção apenas fornece um destino local. Usa o resolvedor existente, o compromisso de rota, o planejador por tentativa e erro, os mesmos testes de percurso e a mesma cápsula de colisão. Não atravessa obstáculos por causa da previsão, não teletransporta e não escreve no World State.

As identidades de jornada mudam ao iniciar, observar e encerrar a busca; interromper um percurso parcial não inventa um custo de jornada bem-sucedida. Recuperação de aprisionamento, perda de feed, pausa ou indisponibilidade do relógio encerram a intenção.

A confirmação de sucesso vem exclusivamente de um novo evento do sensor físico de visão, do mesmo animal e mundo, iniciado depois da tentativa e antes do prazo. O teste com parede comprova que um animal ocluído não confirma a busca.

Encerrar por prazo, falta de progresso ou fim da observação não afirma ausência do animal. A hipótese nunca é enviada como observação à Memoria.ia. Avistamentos reais continuam sendo registrados pela 008DT, independentemente do resultado da intenção.

## Autoridade e apresentação
- `nov_animal_search_intent.gd`: controlador nativo, habilitado explicitamente pelo drop-in de instalação.
- Entrada: checkpoint privado e selado do previsor 008DU, fresco e com mundo/sessão iguais ao gravador de encontros.
- Estado privado 0600: `/var/lib/live-infinita/wildlife/search-policy.json`.
- Projeção pública 0644: `/var/www/live-infinita-godot/wildlife/search-intent.json`.
- Publicação: https://live.etbra.com.br/godot/wildlife/search-intent.json

O privado preserva ordem, orçamento por ciclo, intervalo, intenção ativa, contadores por estratégia e 16 resultados recentes, com checksum e troca atômica. Reinício encerra uma intenção interrompida, sem repetir a tentativa ou zerar limites. Na partida espera o relógio alcançar o checkpoint persistido; retrocesso durante a sessão, corrupção e troca de mundo falham de forma fechada.

A Web não escolhe uma região a partir de informações globais. Consome somente a intenção nativa publicada, com identidade de mundo, origem, autoridade, prazo e coordenadas validados. A intenção expira em até 15 segundos sem heartbeat e respeita o prazo lógico. Durante observação, a rotação visual usa o relógio autoritativo para evitar saltos a cada atualização. Não grava resultados ou experiências da busca no navegador.

No painel existente, o comparativo continua aparecendo quando não há busca. Durante a tentativa, a segunda linha de animais mostra `indo à região` ou `observando`, com `memória` ou `último local`. Narrador central e Explorar oculto são preservados.

O campo do build `nov_animal_memory_decision_use=true` indica esta utilização experimental pela aplicação. A ponte 008DT e o previsor 008DU seguem com `decision_use=false` em seus próprios contratos; a intenção 008DW publica `decision_use=true`. Armazenar, prever e aplicar são camadas distintas.

## Avaliação
Os contadores por estratégia registram tentativas, confirmação pela visão, término sem observação e abandono. Os resultados mantêm previsão e IDs usados, tempos lógicos, alvo pretendido e motivo de término; não fabricam um ID de memória para o avistamento antes de a ponte confirmá-lo.

A comparação prospectiva da 008DU continua funcionando, mas os avistamentos agora podem depender da estratégia de busca escolhida. Acertos nessas condições não devem ser tratados como uma comparação passiva independente nem como melhoria geral já demonstrada.

## Validação e instalação
Suite completa: **37 testes Godot passaram**. Os testes dirigidos foram repetidos após os ajustes finais de validação e apresentação. Cobrem:
- bloqueio por parede e confirmação pelo sensor real;
- resolvedor da cena real, movimento incremental e identidade de percurso;
- respeito à caminhada em andamento, distância e ajuste do alvo;
- orçamento, intervalo, alternância, falta de progresso e observação;
- reinício, espera inicial de relógio, retrocesso, mundo e checkpoint corrompido;
- validade da apresentação Web e interpolação de rotação.

Evidências: `BOUNDED_ANIMAL_SEARCH_RESULT_008DW.json` e logs `BOUNDED_ANIMAL_SEARCH_008DW_*.txt`. Esta validação é isolada: não insere encontros, previsões ou resultados artificiais na produção.

Requer 008DV e 008DU instaladas. O instalador faz backup/rollback dos três scripts nativos, drop-in e export Web; executa os 37 smokes, publica o build e reinicia o renderer. Preserva a população, as memórias, a fila de encontros e o histórico privado das tentativas, inclusive em rollback.

```bash
sudo bash /home/etbra/apply-bounded-animal-search-008dw-root.sh
```

Após instalar, recarregue a fonte da live. Aguardar uma previsão próxima e o fim da caminhada é normal. Caça, reprodução e aprendizagem dos próprios animais não fazem parte desta atualização. Tag e branch de release v0.1.0 permanecem congeladas.
