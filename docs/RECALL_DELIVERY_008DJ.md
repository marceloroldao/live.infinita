# 008DJ — recuperação e painel coerente com a sessão

Verificação da produção: promoções com ACK cresceram até 65; endpoint de recall recuperou 189 rotas (190 no teste HTTP posterior). O teste HTTP com Godot carregou as 190 rotas. O zero no painel não representa banco vazio: a sessão mostrada é do renderer no servidor, mas a contagem de passos era do consumidor no navegador.

O painel agora informa contagens recuperadas do servidor com mundo, origem e prazo do snapshot validados. Sem snapshot válido mostra espera, sem inventar zero. Essas contagens são separadas das escolhas causais: carregar uma rota não significa usá-la. Qualidade só é contada com custos e número de amostras válidos; zero custos não recebe custo inventado.

A consulta de recall tolera quinze segundos e volta a tentar após cinco segundos em falhas de HTTP. A publicação pública aplica permissão 0644 antes da troca atômica; os checkpoints privados continuam 0600. Preserva-se a publicação independente da 008DI1.

Instalação: sudo bash /home/etbra/live.infinita/deploy/apply-recall-delivery-008dj-root.sh

O instalador pausa a sincronização durante a troca do helper e exporter, retomando o timer após ambos. Usa backup/rollback, publica web e reinicia o renderer. Não altera bancos de memória. A validação no navegador do celular segue após aplicar.

Validação: 116 testes Python, 26 verificações Godot, entrega HTTP do painel e teste HTTP de recall da produção passaram. O benchmark isolado com a API real e SQLite confirmou cinco promoções e cinco recuperações em processos separados. Nas dezoito avaliações, todas chegaram, sem colisões e sem busca global. Distância original: 40,5753 m sem memória contra 20,0518 m com RAM ou memória recuperada. Com passo lembrado bloqueado: 53,7431 m contra 30,8435 m. Caminho aberto: 6 m em todos os modos. Isso mede o fixture, não uma melhoria já medida na live.
