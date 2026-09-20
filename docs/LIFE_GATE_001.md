# Life Gate 001 — Nov Autonomous Life v0

## Objetivo

Provar o primeiro comportamento autônomo persistente da Nov no qual uma experiência
anterior muda uma decisão futura sem roteiro semântico dentro da Memoria.ia.

O gate usa a integração experimental do PR #20. A Live.Infinita continua dona do
World State, das ações válidas e das consequências concretas. A Memoria.ia V2 só
preserva experiência estrutural, continuidade situada, previsão e curiosidade.

## Experimento

O cenário possui:

- Nov;
- uma fonte ambiental persistente `source_alpha`;
- uma região de encontro `forest_source_edge`;
- uma região distante `forest_far`;
- uma intervenção exploratória com dois resultados possíveis;
- uma ação de continuação com um único resultado estrutural;
- 16 ticks ambientais entre a saída e o retorno.

Os endereços `alpha` e `beta` são deliberadamente opacos para o núcleo cognitivo.
No produto, a fonte poderá representar água, fogo, vegetação, vento ou outro agente
ambiental. O teste não exige que a Memoria.ia conheça essas categorias.

## Ciclo

```text
encontro inicial
  -> nenhuma continuidade situada estabelecida
  -> intervenção com múltiplos resultados ainda não resolvida
  -> curiosidade seleciona PROBE

segunda observação independente
  -> mesmo contexto + mesma intervenção + mesma consequência
  -> regime situado passa a ativo

Nov sai da região
  -> contexto local deixa de estar ativo
  -> 16 ticks ambientais acontecem
  -> nenhuma nova evidência cognitiva é adicionada

Nov retorna
  -> estado observável pré-ação coincide com o contexto original
  -> regime anterior é recuperado
  -> previsão é resolvida antes de uma nova observação
  -> curiosidade deixa de preemptar o comportamento normal
  -> ação baseline CONTINUE é escolhida
```

## O que o gate prova

1. **Uma observação não vira lei.** São exigidos dois episódios independentes e
   suporte contíguo mínimo 2.
2. **A memória sobrevive à ausência.** O agente pode sair e o mundo pode avançar sem
   destruir o regime situado.
3. **Reconhecimento ocorre antes da nova observação.** A decisão de retorno é somente
   leitura; não cria episódio, evento, delta, versão ou tick.
4. **A memória muda comportamento.** Antes do aprendizado, a curiosidade escolhe
   `probe`; no retorno reconhecido, a exploração é suprimida e o runtime segue a
   ação baseline `continue`.
5. **A Memoria.ia não inventa ações.** Toda ação executada veio de
   `generate_valid_actions()`.
6. **A Memoria.ia não escreve no mundo.** Somente o World Runtime cria Event/Delta.
7. **O resultado é determinístico.** Duas execuções limpas produzem a mesma assinatura.

## Critério de aprovação

O workflow `memoria-v2 cognitive gym` deve executar:

```bash
python -m pytest -q \
  test_memoria_v2_crossrepo.py \
  test_active_curiosity_crossrepo.py \
  test_closed_loop_crossrepo.py \
  test_continuous_closed_loop_crossrepo.py \
  test_life_gate_001_crossrepo.py
```

O Life Gate 001 passa somente se os três testes específicos ficarem verdes:

- memória altera a decisão após o retorno;
- decisão de retorno é read-only até o World Runtime executar;
- execução completa é determinística.

## Limite desta etapa

Ainda não é um agente geral nem um planejador de metas. O gate prova o mecanismo
mínimo `perceber -> explorar -> consolidar -> afastar-se -> retornar -> reconhecer ->
agir diferente`.

A próxima evolução, depois deste gate, é substituir o `baseline continue` por um
scheduler de necessidades/intentos da Nov e introduzir agentes ambientais persistentes
(Água, Vento e Vegetação) usando a mesma fronteira World State <-> Memoria.ia.
