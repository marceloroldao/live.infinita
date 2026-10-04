# 008CI — RAM e promoção por reutilização causal

A 008CH foi confirmada em produção no commit c86e703: cinco execuções
consecutivas bem-sucedidas, 10 episódios com confirmação durável.
As 994 ações então retidas eram originadas da percepção. Esse resultado
comprovava registro, não melhoria por reutilização da memória.

## Política implementada

nov_navigation_working_memory.gd mantém até 512 experiências temporárias
de passos fisicamente concluídos. A chave usa origem e objetivo quantizados
em células de 1 m. A experiência expira após 10 min sem conclusão bem-sucedida.
Leituras não atualizam utilidade nem contam como reutilização.

Uma nova passagem para o mesmo endereço pode substituir a promoção anterior
após acumular novamente três reutilizações causais bem-sucedidas. Repetir
a mesma passagem já promovida não gera novos envios.

Uma experiência temporária entra como candidata do navegador. Seu destino
continua passando pela percepção, validação do solo e varredura de colisão.
Um caminho lembrado que está bloqueado não é selecionado. Uma falha física
invalida a candidata temporária.

Cada seleção é comparada com a seleção feita sem a candidata da RAM, mantendo
as demais percepções, penalidades locais e evidências da Memoria.ia.
Só há suporte para promoção quando:

1. a candidata temporária foi selecionada;
2. o ponto escolhido difere mais de 5 cm da avaliação sem essa candidata;
3. NOV alcançou fisicamente o ponto escolhido;
4. o número da decisão é novo;
5. a mesma experiência acumula três reutilizações bem-sucedidas.

Três é um parâmetro inicial, não uma garantia estatística de utilidade.
Concluir o próximo passo também não comprova chegar ao objetivo final ou
encontrar a rota globalmente mais curta. Esta é uma política de navegação local,
não generalização semântica ou aprendizado por rede neural.

Concordar com a percepção é marcado perception-working-memory-agreement:
esse caso não recebe crédito causal. Leituras repetidas, frames repetidos,
ação interrompida, percepção sem passagem e bloqueio não promovem a candidata.

## Persistência

Experiências temporárias desaparecem no reinício. No modo ao vivo, novos
resumos não são escritos no antigo nov-navigation-008cd.cfg. Os dados antigos
não são apagados e continuam disponíveis como legado.

As promoções e suas três identidades de decisão são salvas atomicamente em
user://nov-navigation-promotions-008ci.json. Promoções pendentes são recarregadas
após reinício; a RAM de experiências não é recarregada. A promoção força
o fechamento da janela de auditoria. As ações guardam working_memory_session,
decision_serial, working_memory_key, working_memory_changed_choice e a
avaliação without_working_memory quando disponível.

nov_navigation_promotion_sync.py envia até duas promoções por execução
para a Memoria.ia local autenticada. Confere identidade do mundo, suporte,
decisões distintas, coordenadas, IDs e ACK durável. O checkpoint só avança
depois do armazenamento confirmado ou duplicata idempotente. O exporter
existente pode recuperar essa promoção pela API para uma decisão futura.

O novo fluxo deixa de enviar indiscriminadamente os resumos antigos e os
episódios completos à Memoria.ia. Os episódios continuam arquivados, completos
e comprimidos, no diretório privado navigation-episodes, para auditoria.
archive_once arquiva todos os episódios retidos sem POST estrutural.
Observações previamente gravadas na Memoria.ia são preservadas.
Não há alteração do núcleo da Memoria.ia nem escrita no estado oficial do mundo.

A janela do renderer continua limitada; uma indisponibilidade prolongada
pode perder episódios antes do arquivamento. Arquivos já arquivados não são
removidos automaticamente. A retenção de disco ainda precisa de política
operacional separada.

## Instalação

Pressupõe a 008CH e a ponte local existentes e funcionando.

    sudo bash /home/etbra/live.infinita/deploy/apply-navigation-working-memory-008ci-root.sh

O instalador guarda backups, valida Python, exporta e testa Godot em cópia
isolada, instala os módulos, reinicia o renderer e publica a cena em /godot/.
A mensagem 008CI_OK confirma ativação. Não exige promoção imediata, porque
isso dependerá das experiências reais de NOV.

Verificar no journal do renderer:

    NOV_WORKING_MEMORY_STATUS entries=N causal_reuses=N promoted=N
    NOV_WORKING_MEMORY_PROMOTED key=... successful_reuses=3

No journal da ponte, promotions.acked e promotions.confirmed mostram a
confirmação da Memoria.ia; episodes.memoria_posts deve permanecer zero.
Não confundir quantidade de entradas, serviços ativos ou ausência de colisão
com prova de melhoria causada pela memória.

## Validação

44 testes Python: suporte insuficiente, decisões repetidas, mundo incorreto,
coordenadas inconsistentes, ACK inválido, repetição após reinício e auditoria
sem POST de episódios, além das verificações existentes de navegação.
Dez testes Godot: física, câmera, apresentação, antecipação, episódios e RAM.
O teste novo comprova seleção influenciada pela RAM, três resultados distintos,
ausência de promoção por consultas, rejeição de rota insegura, expiração,
limites, separação entre mundos e retenção de promoções após reinício.
Movimento real com CharacterBody3D confirma que o sinal de conclusão alimenta
a RAM e que repetir uma escolha já feita pela percepção não promove nada.

A API real da Memoria local, em banco SQLite isolado, recebeu uma promoção
produzida pelo Godot, confirmou duplicata idempotente, devolveu a promoção
pelo recall e preservou seu conteúdo após reabrir o banco.
Auditoria de uma cena isolada conectada ao feed real: auth=true,
connection=conectado, entries=51, causal_reuses=0 e promoted=0.
Comprova preenchimento por ações reais; não comprova melhoria de NOV na live.
A 008CI ainda precisa ser aplicada e observada em produção.
