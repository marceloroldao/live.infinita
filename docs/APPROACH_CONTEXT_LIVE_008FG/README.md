# 008FG — contexto da aproximação na locomoção nativa

A locomoção nativa contornou as cercas que causavam falha no movimento direto de 008FF. As oito aproximações terminaram com aproximação confirmada pela percepção física. Portanto, a vantagem da preferência experimental de 008FF não foi demonstrada nesta condição.

No caso da cerca inicialmente fora da varredura de quatro metros, o alvo próximo exigiu 12,8 m; o distante, 19,4 m. Ambos concluíram, sem contatos físicos e sem construir rota global. Não seria justificável promover a antiga preferência pelo alvo distante para a live.

## Alteração preparada

O renderer coleta a condição física no início da tentativa: perfil de locomoção, varredura de quatro metros, bloqueio à frente e instante lógico. Ao concluir, associa o resultado medido, distância percorrida e contatos reportados pela locomoção. Não há acesso à posição oculta dos animais: o probe recebe o ponto da observação física existente.

Os registros são privados, limitados a 512, com checksum e troca atômica do arquivo. Tentativas censuradas ou sem movimento não são incorporadas ao contexto. O histórico básico de 008FC permanece responsável por tentativas pendentes e interrupções; contexto incompleto não é reconstruído como experiência medida após reinício.

O serviço novo confirma os fatos no núcleo SQLite por identidade estrutural e recupera os registros pela API real. Recibos de gravação não substituem recuperação. O perfil `capsule044-height18-sweep4-native-contour-v1` mantém esses fatos separados dos anteriores de movimento direto.

Esta instalação habilita somente coleta. A escolha de alvo continua a mais próxima entre observações válidas. Não ativa o recomendador experimental, captura ou caça. O status público publica contagens, perfil e `decision_use=false`; nenhum segredo ou registro privado é exposto.

## Validação

- 106 regressões Godot: 53 com os flags ligados e 53 desligados. Logs e resultados on/off nesta pasta.
- 60 testes Python de contratos, ponte e instalação. Resultado em `python-tests.log`.
- Oito trajetos com `world_map_local_motion`: antecipação, guardas de colisão e contorno observados, corpo físico e sensores reais.
- O próprio arquivo selado do coletor Godot foi consumido pela ponte de produção em núcleo isolado: oito fatos nativos confirmados e recuperados.
- Quatro fatos físicos reais de 008FF foram preservados nesse núcleo, sem influenciar os candidatos do perfil nativo.
- Dois reinícios do núcleo recuperaram os mesmos registros sem reingestão.
- Sintaxe Bash, diff e unidades systemd verificados. Nenhum instalador root executado pelo assistente.

O relatório `NATIVE_CONTEXT_VALIDATION_008FG.json` e os arquivos por cenário contêm as medidas. Os testes usam terreno plano, velocidade fixa de 4 m/s e animais parados. Não cobrem streaming do terreno, apresentação completa, velocidade variável da live ou presa fugindo. Não há benefício em produção demonstrado.

## Instalação

Depois do commit/push, o script é disponibilizado em:

```bash
sudo bash /home/etbra/apply-animal-context-008fg-root.sh
```

O instalador exige checkout limpo e serviços anteriores ativos; exporta a apresentação com as regressões, interrompe o renderer antes de substituir os módulos, ativa o flag de coleta e o timer, verifica publicações novas e saudáveis e promove a apresentação. A condição inicial de zero tentativas é válida. Se houver fatos elegíveis, exige confirmação e recuperação do núcleo.

Uma falha retorna os módulos, unidades, flag e apresentação ao backup. Os históricos privados, checkpoints e fatos já gravados no núcleo são preservados. O sucesso termina em `008FG_OK`. A live permanece na versão anterior até a execução pelo operador.

## Próxima evolução

Após verificar a instalação e observar tentativas nativas da live, construir um cenário de falha real nessa locomoção e medir escolhas equivalentes com e sem recuperação do mesmo perfil. Somente depois de demonstrar redução de falhas ou custo deve-se habilitar a influência na escolha do alvo. Generalização para presas móveis exige percepção temporal e resultados de perseguição próprios.
