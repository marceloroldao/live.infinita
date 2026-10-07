# 008DX — auditoria das buscas de animais

Ferramenta de leitura para comparar as tentativas nativas por memória e por último local observado, sem escolher destinos, reiniciar serviços ou escrever na memória. Não altera o núcleo congelado, a física ou a interface da live.

```bash
python3 /home/etbra/live.infinita/tools/audit_animal_search_008dx.py
```

Lê os três JSON públicos locais. Rejeita dados com mais de 15 segundos, relógios futuros além da tolerância de cinco segundos, mundos diferentes, origem ou autoridade incorreta e erros das fontes. Exige consistência dos contadores com a intenção ativa e das confirmações com os prazos. Não transforma ausência de tentativas em precisão zero.

Os totais são cumulativos; as durações e o cruzamento com encontros recuperados pertencem à janela de até 16 resultados. Um encontro ausente da janela de recuperação é indicado como não localizado nessa janela, sem afirmar falha de armazenamento. Um resultado confirmado exige a identidade do animal e o mesmo instante lógico do primeiro avistamento para cruzar com o encontro recuperado.

Tentativas ainda em andamento ficam fora do denominador de resultados concluídos. Desistências permanecem nesse denominador. A comparação das previsões é apresentada separadamente; seus avistamentos podem ser influenciados pelas buscas ativas. A alternância não é randomizada e a ferramenta não declara vantagem causal ou aprendizagem geral.

Validação: cinco testes de ausência de amostras, tentativa ativa, fonte antiga/mundo incorreto/autoridade, contadores inconsistentes, encontro confirmado/fora da janela e resultado duplicado. Também executada com os dados reais de produção, sem injetar eventos.

Captura inicial: uma busca pela memória, confirmada em 5.992 segundos lógicos e associada ao encontro recuperado; nenhuma busca pelo último local. 92 encontros armazenados e recuperados. A ferramenta fica disponível na VM e no GitHub; nenhum instalador root é necessário.

## Acompanhamento de validade

O relatório agora classifica as previsões pelo tempo lógico atual: vencidas, com menos de 20 segundos restantes e elegíveis pelo prazo. Previsões vencidas podem permanecer no JSON durante a espera pela confirmação de encontros; não são tratadas como disponíveis para uma nova busca. A próxima estratégia é indicada pela alternância persistida. Distância, conclusão da jornada, visibilidade e aceitação física não são inferidas a partir desses JSON.

Sete testes passaram após esta extensão. Na nova captura havia 94 encontros recuperados, uma busca pela memória confirmada, nenhuma pelo último local e duas previsões vencidas. O acompanhamento do renderer encontrou seis recuperações por aprisionamento entre 09:51 e 10:18:45 de Brasília, sem erros de script. Investigar a navegação passa a ser prioridade; não atribuir esses retornos a aprendizagem bem-sucedida. Nenhuma regra de movimento ou busca foi alterada neste acompanhamento.
