# 008CN — Destino local estável e continuidade dos passos

A auditoria 008CM encontrou 813 ações em 223,1 segundos, com 758 passos
concluídos, 55 interrupções e nenhum destino alcançado na janela.
Esse resultado confirma reutilização causal de RAM, mas não demonstra
melhora de rotas completas na live.

## Comportamento

O renderer assume uma posição observada do feed como destino local.
Atualizações seguintes não substituem esse destino durante a caminhada.
Ao chegar a menos de 0,1 m, ele escolhe a posição mais recente do feed.
Depois de 180 segundos de movimento processado, reavalia o destino.
Troca de mundo ou saída do modo live reinicia o compromisso.
Posições não finitas não iniciam rotas.

A identidade de rota é sessão aleatória mais contador e acompanha
os registros de ações. O validador Python aceita arquivos antigos sem
esse campo, preserva identidades válidas e rejeita valores inválidos.
Uma troca de identidade libera o passo local para decidir pelo novo destino.

A atualização ou expiração do recall limpa/substitui as evidências para
a próxima decisão sem cancelar o passo físico ativo. Cada avanço continua
a verificar travessabilidade e colisão; um bloqueio ainda interrompe o passo.

O destino representa uma posição anterior observada do runtime, portanto
a apresentação pode ficar defasada enquanto conclui o percurso. O limite
de 180 s usa delta processado, limitado a 0,1 s por quadro, não tempo de
parede em caso de pausa ou baixo FPS. Não há alteração do World State,
planner global, garantia de saída de qualquer obstáculo, ou novos objetivos
semânticos.

## Verificação

- 62 testes Python de navegação passaram, incluindo preservação e rejeição
  de identidades de rota e compatibilidade com episódios antigos.
- Teste Godot do controlador: chegada, troca de mundo, limite de tempo,
  destino não finito e ausência de chegadas repetidas quando parado.
- Teste de recall: atualizar ou expirar evidência preserva o passo ativo.
- Obstáculo físico em U: percurso até o destino original concluído com
  zero colisões, apesar de posições alternadas do feed.
- Integração na cena live: destino e identidade permanecem estáveis
  depois de atualização do feed e do recall.
- Os 12 testes Godot da publicação passaram, sem erros de script,
  incluindo caminhada, câmera, colisões, episódios, RAM e residência local.

O teste controlado não comprova ganhos na produção. Após instalar,
auditar destinos alcançados, interrupções, colisões e reutilização causal
por rota. Só comparar custo entre percursos equivalentes e observados.

## Aplicação

Execute como root:

```bash
cd /home/etbra/live.infinita
git pull --ff-only
sudo bash deploy/apply-stable-route-goal-008cn-root.sh
```

O instalador atualiza primeiro a ponte de memória com validação compatível
e depois o renderer nativo e a exportação Web. Cada etapa usa o rollback
do respectivo instalador. Se a segunda etapa falhar, a ponte nova compatível
pode permanecer instalada, enquanto a versão anterior do renderer é restaurada.
Os dados duráveis já confirmados não são removidos.

Log do renderer: /home/etbra/008cn-renderer-rollout.log.
Sucesso final: 008CN_COMPLETE. A publicação exige os testes Godot e
confere o commit no build público, os novos indicadores, o serviço ativo
e a saúde do runtime.
