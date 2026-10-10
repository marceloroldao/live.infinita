# 008FH — falha e reavaliação com locomoção nativa

Experimento isolado com a locomoção completa de Nov, percepção física, coletor de contexto de 008FG, ponte de produção e núcleo SQLite real reaberto após cada fato. Nenhum código, política ou dado privado da live foi alterado.

## Resultado observado

Uma cerca baixa de 80 m começa a seis metros de Nov, além da varredura inicial de quatro metros. Os dois coelhos são fisicamente visíveis no início. A cerca não recebe rótulo cognitivo: a locomoção encontra o obstáculo e contorna; a tentativa termina em perda de contato quando o desvio leva o alvo além do alcance do sensor.

Quatro aproximações iniciais, duas por opção, são agendadas pelo experimento. Esses resultados medidos entram pelo arquivo selado real do coletor e são confirmados e recuperados do núcleo. Esse agendamento é aquisição balanceada externa; não deve ser chamado de exploração autônoma.

Na comparação estável, com as mesmas observações e estado físico inicial:

| Condição | Escolha | Resultado |
|---|---|---|
| Percepção / memória vazia | Coelho mais próximo | Perda de contato |
| Fatos recuperados do mesmo perfil | Outro coelho visível | Aproximação confirmada |

O seletor existente pondera explicitamente distância medida e falhas por contexto: faixa de distância, perfil de locomoção e bloqueio observado. A Memoria.ia armazena e recupera os fatos estruturais; a regra de escolha pertence ao seletor experimental. O núcleo não escolhe alvos sozinho.

Invertida a orientação da cerca, ambos os contextos iniciais continuam com varredura livre. A escolha antiga não antecipa a mudança oculta e falha. Após registrar e recuperar essa falha, o seletor escolhe três tentativas de reavaliação: próximo, distante, próximo. Seus resultados são sucesso, perda de contato, sucesso.

A escolha final volta ao próximo e coincide com a percepção. Essa etapa demonstra revisão da preferência anterior; não representa ganho adicional sobre a percepção nessa configuração invertida.

## Evidência e reprodução

- 12 aproximações físicas com antecipação, guardas de colisão e contorno local ativos.
- Oito resultados efetivamente gravados e recuperados pela API estrutural do núcleo SQLite, sem fallback.
- Oito recuperações após reabertura do núcleo e remoção do cache de leitura, sem POST nessa fase.
- Três escolhas de reavaliação derivadas dos fatos recuperados.
- Sem contatos físicos, construção de rota global ou captura.
- Arquivo original do coletor preservado por tentativa concluída; nenhum resultado sintético é passado como movimento real.
- Relatório `NATIVE_FAILURE_REASSESSMENT_008FH.json` reúne decisões, referências dos fatos, medidas, controles e limitações.

Reproduzir sem sudo:

```bash
cd /home/etbra/live.infinita
/opt/live.infinita/.venv/bin/python tools/run_native_failure_reassessment_008fh.py --output-dir /home/etbra/008fh-repeat
```

O teste usa núcleo, checkpoints e diretório de dados Godot temporários. Não requer instalação na live.

## Limites

Terreno plano, velocidade fixa de 4 m/s, dois animais parados e uma família determinística de barreiras. Durante a aproximação, o sensor acompanha o último ponto observado; esse controle de atenção não reproduz a câmera completa da live. As regras de amostragem e pontuação são explícitas e o contexto é grosseiro.

O resultado demonstra diferença entre decisões com e sem fatos recuperados neste experimento. Não demonstra melhoria na live, generalização para outras geometrias ou aprendizagem de caça.

Na live, 008FG continua apenas coletando contexto; a consulta inicial desta etapa encontrou zero novas aproximações contextuais e nenhuma falha de serviço. A instalação anterior não foi reiniciada nem modificada para forçar experiências.

## Próximo passo

Testar transferência para novos animais e variar velocidades e geometria. Depois reproduzir a atenção e a câmera reais da live antes de habilitar o seletor contextual em modo reversível. A coleta de produção deve produzir evidência própria antes de qualquer alegação de ganho ao vivo.
