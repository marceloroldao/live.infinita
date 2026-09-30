# Vale de Nov — navegação e vínculo explícito ao World State (contrato)

Esta etapa não integra o mapa 3D à live e não modifica o Nov real.
A nova classe `WorldMapNavigation` lê o manifesto visual e fornece:

- endereços estáveis para os 256 setores (`vale-nov/v1/XX/ZZ`);
- indexação por posição aritmética em vez de varrer o universo;
- seleção de no máximo 3×3 setores ao redor da posição autorizada;
- caminhos determinísticos em quatro direções, com o rio bloqueado
  exceto pela ponte no setor (8,7);
- coordenadas dos pontos de interesse e projeção explicitamente read-only.

## Atenção à diferença de referenciais

O estado legado opera em coordenadas 2D x/y e utiliza `region_id`
como `clearing`, `deep_forest` etc. Já o cenário Godot usa X/Z,
com origem no centro de um terreno de 1.024 m por lado. Uma posição
legada 360,300 não pode ser interpretada diretamente como X=360,Z=300.

Para obter uma projeção, o Nov **autoritativo** deverá carregar,
por uma migração futura validada pelo runtime:

```json
{
  "id": "nov",
  "position_frame": "vale-nov/v1",
  "region_id": "vale-nov/v1/05/07",
  "position": {"x": -160.0, "y": -32.0}
}
```

O contrato interpreta apenas `position.y` como Z visual se
`position_frame` e `region_id` coincidirem. Sem essa evidência,
retorna `unbound` com motivo específico. Não adivinha, não altera
o mundo, não seleciona trajetória e não dá autoridade ao renderer.

## Caminho até a integração efetiva

1. Materializar as novas regiões no armazenamento autoritativo,
   mantendo a migração reversível e sem sobrescrever identidade antiga.
2. Introduzir o referencial da posição como parte do contrato de
   movimento, sob a política de mutação do World Runtime.
3. Associar POIs estáveis a entidades concretas, sem transformar
   modelos glTF em dados da Memoria.ia.
4. Usar o planejador para gerar uma **proposta** de deslocamento;
   só o writer autoritativo poderá efetivar cada transição.
5. A câmera 3D acompanhará a posição confirmada recebida por
   leitura de estado, sem realizar movimentos simulados por conta própria.

O script não é importado no runtime existente e mantém o PR #112 em
modo rascunho. Sua API é preparatória, não um cutover.

## Teste

```bash
python -m unittest -q tests.test_world_map_navigation
```
