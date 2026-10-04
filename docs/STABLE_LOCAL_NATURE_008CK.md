# 008CK — objetos estáveis na caminhada

As camadas de natureza calculavam posições a partir da posição/direção de Nov e eram recriadas a cada 9–10 metros ou mudança de direção. Isso deslocava árvores, pedras e plantas já visíveis, inclusive seus obstáculos físicos.

Agora cada camada tem candidatos determinísticos em coordenadas do terreno e registros residentes. Depois da população inicial, novas entradas só são admitidas a pelo menos 45 m de Nov. Um registro existente nunca é descartado para abrir espaço no orçamento nem em função da direção da câmera, da densidade ou de uma nova região. Só é removido além do raio de retenção. Transformação e espécie ficam congeladas enquanto residentes; árvores comuns e pinheiros coexistem em batches diferentes, com o mesmo limite total de objetos visíveis por camada.

| Camada | Carregar até | Remover além de | Limite |
|---|---:|---:|---:|
| Árvores detalhadas | 60 m | 85 m | 14 |
| Árvores intermediárias reais | 85 m | 110 m | 18 |
| Plantas detalhadas | 50 m | 75 m | 40 |
| Pedras detalhadas | 60 m | 85 m | 18 |
| Árvores procedurais | 100 m | 125 m | 44 |
| Plantas procedurais | 75 m | 100 m | 220 |
| Vegetação intermediária simples | 94 m | 120 m | 180 |
| Árvores distantes simples | 390 m | 430 m | 120 |

As colisões das camadas físicas acompanham exatamente suas transformações residentes. O antigo corredor que retirava árvores conforme a direção foi substituído por posições estáveis; Nov usa a percepção física e a navegação existentes para desviar.

Na atualização cognitiva do terreno, setores que interceptam o raio de 45 m conservam sua geometria e decoração. A altura de caminhada é interpolada dos vértices realmente renderizados de cada setor residente, preservando o alinhamento dos pés mesmo se o alvo cognitivo mudar. Setores mais distantes são renovados; o cache distante é invalidado. As atualizações próximas ficam adiadas, podendo ser incorporadas quando o setor sair da área e for carregado novamente ou numa atualização posterior distante. O World State permanece intacto.

A estabilidade é local à sessão do renderer. Não é um inventário persistente de objetos na Memoria.ia. Fora da área protegida ainda há carregamento/descarregamento, limites de instâncias e recorte pela câmera. A atualização pode alterar a densidade visual próxima durante a primeira inicialização da nova versão.

Validação: 12 testes Godot, incluindo longa caminhada de 79 deslocamentos, identidade/posição preservada, chegada somente além de 45 m, descarregamento distante, troca de clima preservando espécie, colisores iguais à renderização, setores próximos preservados e testes de navegação/câmera/episódios/RAM. Os testes antigos que fixavam anéis e corredor relativos ao observador foram substituídos pela verificação comportamental de residência.

Instalação: `sudo bash /home/etbra/live.infinita/deploy/apply-stable-local-nature-008ck-root.sh`. Faz export em cópia isolada, valida os testes antes de publicar, instala também o renderer nativo, verifica metadados públicos e saúde e mantém backup/rollback. Sucesso: `008CK_OK`.
