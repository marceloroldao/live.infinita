# 008ER — integração das janelas adaptativas

Integra a política renovável da 008EQ em nov_navigation_patterns.gd. O avaliador completo anterior continua disponível. A opção cost_shift_enabled inicia desligada; o coletor nativo lê LIVE_INFINITA_NAVIGATION_COST_SHIFT=1. O instalador configura o serviço nativo com a opção ligada, e o estado de aprendizado informa patterns.cost_shift_enabled. O Web export anuncia a capacidade e a autoridade native_renderer_configured; esse flag de build não é uma confirmação de que o serviço está atualmente ligado. O navegador sem configuração de ambiente mantém a política anterior. As decisões da sessão exibidas pela live continuam sob autoridade nativa.

Quando o custo físico cresce mais de 50% e mais de 3 m frente à referência de duas amostras daquele lado na janela, o avaliador inicia uma janela nova. Guarda a observação que detectou o crescimento, exige duas experiências reais em cada lado e reavalia a preferência. Cada novo crescimento pode renovar a janela. Exploração usa source=pattern-exploration, não recebe crédito como preferência aprendida e nunca cria um resultado físico pela mera proposta.

A física e seus bloqueios permanecem obrigatórios. Distâncias medidas, penalidade de erros, margem, perfil v3, schema v2, armazenamento 008ej, transporte, IDs, checkpoint, cache e núcleo local permanecem compatíveis. Todos os registros anteriores são mantidos; desativar a opção volta a avaliar o histórico completo, incluindo experiências acumuladas desde a atualização.

## Validação

47 regressões passaram com a configuração desligada e 47 com ela ligada. Após corrigir um conflito de nomes dos constantes com os testes experimentais anteriores, os 47 testes com a opção ligada foram executados novamente na versão final, e o teste histórico 008EQ passou. Os registros estão nos arquivos COST_WINDOWS_REGRESSIONS_*_008ER.

O teste físico usa a implementação integrada, selecionada pela configuração real do coletor, sem substituir o avaliador por uma classe experimental. Reproduziu exatamente a sequência 008EQ (-20, -110, 0, -20), suas escolhas e distâncias: 5801.48 m nas 48 tentativas, contra 7570.83 m da política anterior no fixture. Zero colisões, resgates e buscas globais. Guardou 52 fatos físicos em núcleo SQLite isolado real, reabriu o núcleo, removeu o cache e recuperou os 52 sem reingestão. O teste posterior confirmou cost_shift_enabled=true e recomendação recuperada com IDs reais. A recuperação coincide com a percepção no estado final, não demonstra ganho causal adicional.

O resultado é de uma sequência determinística de parede plana, sem ruído, relevo ou obstáculos múltiplos. A terceira fase tem custo de exploração extra, incluído no saldo da sequência. Não é garantia de melhoria na live. Os limiares são escolhas da política, não parâmetros aprendidos pelo núcleo.

## Instalar e controlar

Aplicar na VM:

```bash
sudo bash /home/etbra/apply-adaptive-cost-windows-008er-root.sh
```

Desligar ou religar depois:

```bash
sudo bash /home/etbra/set-cost-shift-008er-root.sh off
sudo bash /home/etbra/set-cost-shift-008er-root.sh on
```

O controle reinicia o renderer e confirma a opção no novo status. Não apaga memória ou histórico. Tem restauração automática da configuração anterior se o renderer não confirmar o estado solicitado.

O instalador faz backup do código nativo, export web, unidades da ponte e configuração da opção; pausa a ponte; exporta com 47 regressões; instala o código; ativa a configuração e reinicia o renderer. Confirma estado nativo recente, coletor habilitado com cost_shift_enabled=true, schemas/perfil, ponte com Result=success e fonte pública correta. Falha provoca rollback automático do código, site e configuração. Memória, fauna, encontros e buscas não são apagados.

Log: /home/etbra/008er-adaptive-cost-windows-rollout.log.
Backups: /opt/live.infinita/.rollouts/008er-<UTC>.
Configuração: /etc/systemd/system/live-infinita-renderer.service.d/99-navigation-cost-shift-008er.conf.

Os scripts foram revisados, passaram em bash -n e possuem cópias executáveis iguais em /home/etbra. Nenhum comando root foi executado pelo Codex; a instalação em produção permanece pendente do comando acima. A live ainda usa a 008EM.

Após aplicação, verificar a versão pública, serviço, opção efetiva, memória preservada, recibos do núcleo e decisões/saídas físicas. O medidor 008EL continua distinguindo percepção, exploração, recomendações aplicadas e contatos excluídos. Não foi criado monitoramento automático.
