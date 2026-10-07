# Memória de avistamentos — 008DT

Nov passa a registrar somente encontros produzidos por seu sensor físico de visão 008DR/008DS1. O gravador não lê o arquivo global da população e não recebe posições de animais ocultos. A espécie e a identidade continuam rótulos fornecidos pelo cadastro, não identificação visual aprendida.

## O que vira experiência

Avistamentos consecutivos do mesmo animal são agregados em encontros de até 30 segundos lógicos. Um encontro termina após três segundos lógicos sem avistamento, ao fechar a janela ou quando o renderer retoma um encontro interrompido por reinício. O motivo `lost_visual_contact` significa apenas perda de contato visual; não afirma ausência de animais na região e não é uma busca fracassada.

Cada registro inclui primeiro/último instante realmente visto, posições observadas do animal e dos olhos, número de amostras, menor/maior distância e alcance do sensor. Não inclui fome, sede, destino, localização posterior ou outros estados internos dos animais. Frames repetidos com o mesmo instante lógico e recuo de relógio não geram amostras extras. Outro mundo não se mistura ao diário.

A fila persiste em `wildlife/encounters.json`, 0600, com payload e SHA-256 e substituição atômica. Há até 128 encontros pendentes e 16 ativos. Os pendentes não são descartados para aceitar novos encontros; se a memória ficar indisponível e a fila encher, novas amostras são suspensas e contabilizadas. Não há perda silenciosa da fila. O checkpoint guarda sessão e sequência para retomada.

## Memoria.ia real

Uma nova ponte local envia no máximo um encontro por execução à API estrutural congelada. Usa a chave existente sem alterar o núcleo. O evento tem identidade derivada do conteúdo, sessão e sequência. Repete a mesma identidade após timeout ou falha antes do checkpoint. JSON do Godot converte inteiros em floats ao recarregar; a ponte normaliza os campos numéricos para preservar a identidade entre reinícios.

Após ACK de armazenamento/duplicata válido, a ponte recupera o registro da API e confere identidade, evento, proveniência e payload. Só então escreve o cursor confirmado em `encounters-ack.json`, 0600. O renderer pode liberar esses registros da fila. A ponte e o renderer escrevem arquivos distintos. O histórico recente de 16 registros recuperados fica no status público; o armazenamento da Memoria.ia conserva os eventos anteriores.

O endpoint congelado oferece recuperação dos últimos 100 registros, sem busca direta por ID. Se um encontro sair dessa janela antes da verificação, fica pendente com erro explícito, sem ser contado como recuperado. Um lookup por ID é uma extensão futura do adaptador. Não há leitura direta do banco ou alteração do núcleo para contornar isso.

O timer executa a cada cinco segundos após a conclusão anterior, sem sobreposição; orçamento de POST 30 s, GET 15 s, processo 65 s. Sem novos encontros, verifica a API no máximo uma vez por minuto. A ponte não escreve World State, não muda animais, não escolhe destinos e não usa o previsor climático.

## Validação e limites

O teste Godot usa sensor real, um alvo visível, outro fora do alcance e uma parede física. Exercita agregação, pausa/replay, perda de contato, tempo do último avistamento, persistência, confirmação com cursor limitado, janela de 30 s e rejeição de outro mundo/corrupção.

35 testes Godot de regressão passaram, incluindo visão, população real, colisões, caminhada, câmera, água/ponte, terreno, céu e clima. Os 15 testes Python cobrem geometria, proveniência, tempo, sequência, corrupção, ACK falso, timeout após gravação, falha na recuperação, deduplicação numérica e processamento limitado. Um encontro gerado pelo teste Godot é enviado à API do núcleo congelado em armazenamento isolado: é realmente gravado e recuperado. Uma falha após gravação/recuperação e antes do checkpoint é repetida após reabrir o núcleo e conserva somente um registro. Nenhum dado de teste entra na memória de produção.

Isto comprova o mecanismo de registro e recuperação, não uma previsão melhor ou mudança das escolhas de Nov. Ainda faltam buscas delimitadas, escolha de onde procurar com base em experiências e comparação prospectiva com/sem memória.

## Instalação e acompanhamento

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-animal-encounter-memory-008dt-root.sh
```

Sucesso: `008DT_OK`. O instalador mantém backup/rollback, verifica o gravador nativo e a ponte/API sem inventar avistamentos. Um contador zero após a instalação é normal até Nov realmente enxergar os animais e completar encontros. Preserva população, fila e memórias confirmadas; não reinstala serviços climáticos.

Status público: `/godot/wildlife/encounter-memory.json`. `stored_and_recovered_encounters` exige gravação e recuperação verificadas, `pending` mostra fila ainda não confirmada, `active_encounters` mostra encontros abertos, `last_error` mostra falha atual. Em falha da ponte, os contadores são omitidos para não apresentar valores não verificados como atuais. O painel principal da live ainda não ganha um contador de caça nesta etapa.
