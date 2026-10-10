# 008FE — Comparação física de escolhas com fatos recuperados

Experimento isolado de seleção de alvo para aproximação. A live permanece em 008FC + ponte 008FD; nenhuma estratégia nova foi instalada no servidor de produção.

## Cenário e comparação
Dois coelhos estáticos são vistos simultaneamente por raios reais do sensor Godot. Um está a 10 m, outro a cerca de 18,87 m. Uma cerca baixa permite avistamento, mas bloqueia a cápsula física. Cada tentativa executa passos incrementais de CharacterBody3D e encerra pelo controlador real 008FC. Contatos com a cerca são medidos; Nov não atravessa a cerca. Os estados iniciais são resetados entre episódios isolados, sem contar reposicionamento como distância percorrida.

O controle usa o seletor original, com os dois avistamentos disponíveis, que escolhe o animal mais próximo. O braço experimental utiliza os mesmos dois candidatos e seleciona por experiência recuperada. A identidade e as distâncias iniciais dos avistamentos são verificadas iguais entre os braços.

O seletor experimental agrupa por faixa de distância inicial de 6 m, sem usar identidade do animal ou rota gravada. Exige duas experiências distintas em cada faixa candidata, utiliza as duas mais recentes e pontua distância/3 mais uma penalidade de 20 para resultados sem aproximação confirmada. Uma mudança exige pontuação mais de 20% menor. Estes parâmetros são escolhas de política do experimento, não parâmetros aprendidos pelo núcleo.

## Resultado observado
| Situação | Percepção pela distância | Experiência recuperada |
|---|---|---|
| Cerca bloqueia a opção próxima | Falha por falta de progresso | Aproximação concluída da opção distante |
| Cerca passa a bloquear a opção distante | Aproximação concluída | Preferência antiga falha por falta de progresso |
| Após novas experiências nas duas opções | Aproximação concluída | Escolha volta à opção próxima; mesma ação do controle |

14 tentativas físicas: quatro para aquisição inicial balanceada, três pares comparativos e quatro para aquisição após mudança. Oito resultados de aquisição foram gravados no SQLite real do SDK congelado dfd87c995b50c49b45a9d5dd4c43cce456983d4f, com allow_fallback=false. O núcleo foi reaberto e o recall removido duas vezes; os mesmos fatos voltaram pela API sem nova ingestão. A decisão verifica os identificadores completos dos fatos recuperados e rejeita duplicações e alterações.

O primeiro par demonstra mudança causal de escolha e de conclusão da tarefa neste cenário construído: com a mesma percepção, os fatos recuperados permitiram escolher a alternativa alcançável. O segundo é um contraexemplo medido: a experiência antiga piorou a decisão após a mudança. No terceiro, as experiências recentes mudaram a preferência anterior, mas a ação final coincide com a percepção, portanto não se atribui ganho adicional à memória nessa comparação.

## Limites e próxima evolução
O experimento utiliza movimento direto com colisões, não a navegação completa com contorno da cena de produção. Os coelhos não fogem. A aquisição alternada entre opções foi agendada pelo teste; ainda não existe uma política autônoma de exploração de caça. São pares determinísticos de uma única família de cenário, sem estimativa estatística de melhoria geral.

Faixa de distância é contexto insuficiente: não descreve terreno, obstáculos ou comportamento do animal. A evidência pede registrar contexto físico observado, separar perda de contato de bloqueio, reavaliar preferência após falha e explorar alternativas quando o cenário muda. A recuperação do núcleo alimenta um seletor consumidor explícito; o núcleo não decide sozinho. Ainda não há captura nem benefício comprovado na live.

Arquivos: `APPROACH_CHOICE_008FE/APPROACH_CHOICE_008FE.json`, oito fatos medidos, os três pares, logs físicos e contratos. O runner reproduz o experimento com:
`/opt/live.infinita/.venv/bin/python tools/run_approach_choice_008fe.py --output-dir /home/etbra/008fe-reproduction`

Validação concluída: 27 contratos Python passaram; 14 tentativas físicas concluídas sem erros de script; duas recuperações frias do núcleo verificadas. Código e evidências versionados juntos.
